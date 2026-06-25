import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_hospital
from app.core.email import send_account_credentials
from app.core.security import verify_password, create_access_token, create_refresh_token
from app.models.hospital import Hospital
from app.crud.hospital import (
    get_hospital_by_loginid,
    get_hospital_by_credentials,
    update_hospital_password,
)
from app.crud.doctor import get_doctors_by_hospital, get_doctor_by_license
from app.db.session import get_db
from app.utils.rate_limit import rate_limit
from app.schemas.doctor import (
    DoctorLoginRequest,
    DoctorTokenResponse,
    DoctorTokenRefreshRequest,
    DoctorPasswordChangeRequest,
    DoctorPasswordResetRequest,
    AccountInquiryRequest,
)

router = APIRouter(prefix="/doctor/auth", tags=["doctor-auth"])


def _temp_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(10))


# 수의사(병원) 로그인
@router.post("/login", response_model=DoctorTokenResponse)
async def doctor_login(request: DoctorLoginRequest, http_request: Request, db: AsyncSession = Depends(get_db)):
    # 무차별 대입(brute-force) 차단 — IP당 분당 10회. (guardian login 과 동일 정책)
    rate_limit(http_request, key="doctor-login", limit=10, window_sec=60)
    hospital = await get_hospital_by_loginid(db, request.loginid)

    if not hospital or not verify_password(request.password, hospital.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    access_token  = create_access_token({"sub": str(hospital.hospitalid), "type": "hospital"})
    refresh_token = create_refresh_token({"sub": str(hospital.hospitalid), "type": "hospital"})

    doctors = await get_doctors_by_hospital(db, hospital.hospitalid)
    main_doctor = doctors[0] if doctors else None

    return DoctorTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        is_initial_password=hospital.is_initial_password,
        hospital_name=hospital.hospital_name,
        doctor_name=main_doctor.doctor_name if main_doctor else None,
        license_number=main_doctor.license_number if main_doctor else None,
        hospital_number=hospital.hospital_number,
        business_number=hospital.business_number,
    )


# 수의사(병원) 토큰 갱신
@router.post("/refresh")
async def doctor_refresh_token(request: DoctorTokenRefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(request.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        hospital_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        if hospital_id is None or token_type != "hospital":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다.")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="토큰이 만료되었거나 유효하지 않습니다.")

    result = await db.execute(select(Hospital).where(Hospital.hospitalid == int(hospital_id)))
    hospital = result.scalar_one_or_none()
    if not hospital:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="존재하지 않는 병원입니다.")

    new_access_token = create_access_token({"sub": hospital_id, "type": "hospital"})
    return {"code": 200, "message": "토큰이 갱신되었습니다.", "result": {"access_token": new_access_token}}


# 비밀번호 변경
@router.put("/password/change")
async def change_password(
    request: DoctorPasswordChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    if request.new_password != request.new_password_confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="새 비밀번호가 일치하지 않습니다.",
        )

    if not verify_password(request.current_password, current_hospital.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 비밀번호가 올바르지 않습니다.",
        )

    await update_hospital_password(db, current_hospital, request.new_password)
    return {"code": 200, "message": "비밀번호가 변경되었습니다."}


# 비밀번호 재설정 (loginid + 면허번호로 본인 확인)
@router.post("/reset-password")
async def reset_password(request: DoctorPasswordResetRequest, db: AsyncSession = Depends(get_db)):
    hospital = await get_hospital_by_loginid(db, request.loginid)
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="입력하신 정보와 일치하는 계정을 찾을 수 없습니다.",
        )

    doctor = await get_doctor_by_license(db, hospital.hospitalid, request.license_number)
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="입력하신 정보와 일치하는 계정을 찾을 수 없습니다.",
        )

    temp = _temp_password()
    await update_hospital_password(db, hospital, temp)
    hospital.is_initial_password = True
    await db.commit()

    return {"code": 200, "message": "임시 비밀번호가 발급되었습니다.", "result": {"temp_password": temp}}


# 계정 문의 (병원명 + 사업자번호 + 면허번호 → 이메일 발송)
@router.post("/account-inquiry")
async def account_inquiry(request: AccountInquiryRequest, db: AsyncSession = Depends(get_db)):
    hospital = await get_hospital_by_credentials(db, request.hospital_name, request.business_number)
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="병원명 또는 사업자등록번호가 일치하지 않습니다.",
        )

    doctor = await get_doctor_by_license(db, hospital.hospitalid, request.license_number)
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="의사면허번호가 일치하지 않습니다.",
        )

    if not hospital.owner_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="등록된 대표 이메일이 없습니다. 관리자(aoj.medipaw@gmail.com)에게 직접 문의해주세요.",
        )

    temp = _temp_password()
    await update_hospital_password(db, hospital, temp)
    hospital.is_initial_password = True
    await db.commit()

    send_account_credentials(
        doctor_email=hospital.owner_email,
        doctor_name=doctor.doctor_name,
        hospital_name=hospital.hospital_name,
        loginid=hospital.loginid,
        temp_password=temp,
    )

    return {"code": 200, "message": "등록된 대표 이메일로 계정 정보를 발송했습니다."}


# 같은 병원 소속 수의사 목록
@router.get("/hospital/doctors", status_code=200)
async def list_hospital_doctors(
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    doctors = await get_doctors_by_hospital(db, current_hospital.hospitalid)
    return {
        "code": 200,
        "result": [
            {"doctorid": d.doctorid, "doctor_name": d.doctor_name}
            for d in doctors
        ],
    }
