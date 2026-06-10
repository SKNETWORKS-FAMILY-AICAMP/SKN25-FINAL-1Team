from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import secrets
import string
from app.db.session import get_db
from app.schemas.doctor import DoctorLoginRequest, DoctorTokenResponse, DoctorPasswordChangeRequest, DoctorPasswordResetRequest, AccountInquiryRequest
from app.crud.doctor import get_doctor_by_loginid, update_doctor_password, reset_doctor_password, get_doctor_by_inquiry, get_doctors_by_hospital
from app.core.email import send_account_credentials
from app.core.security import verify_password, create_access_token, create_refresh_token, hash_password
from app.core.dependencies import get_current_doctor

router = APIRouter(prefix="/doctor/auth", tags=["doctor-auth"])

# 수의사 로그인
@router.post("/login", response_model=DoctorTokenResponse)
async def doctor_login(request: DoctorLoginRequest, db: AsyncSession = Depends(get_db)):
    doctor = await get_doctor_by_loginid(db, request.loginid)

    if not doctor or not verify_password(request.password, doctor.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다."
        )

    access_token = create_access_token({"sub": str(doctor.doctorid), "type": "doctor"})
    refresh_token = create_refresh_token({"sub": str(doctor.doctorid), "type": "doctor"})

    return DoctorTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        is_initial_password=doctor.is_initial_password,
        license_number=doctor.license_number,
        hospital_number=doctor.hospital_number,
        business_number=doctor.business_number,
    )

# 비밀번호 변경
@router.put("/password/change")
async def change_password(
    request: DoctorPasswordChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_doctor = Depends(get_current_doctor)
):
    # 새 비밀번호 일치 확인
    if request.new_password != request.new_password_confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="새 비밀번호가 일치하지 않습니다."
        )

    # 현재 비밀번호 확인
    if not verify_password(request.current_password, current_doctor.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 비밀번호가 올바르지 않습니다."
        )

    await update_doctor_password(db, current_doctor, request.new_password)
    return {"code": 200, "message": "비밀번호가 변경되었습니다."}

# 비밀번호 재설정
@router.post("/reset-password")
async def reset_password(request: DoctorPasswordResetRequest, db: AsyncSession = Depends(get_db)):
    doctor = await reset_doctor_password(db, request.loginid, request.license_number)

    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="입력하신 정보와 일치하는 계정을 찾을 수 없습니다."
        )

    # 임시 비밀번호 생성
    temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits + "!@#$%") for _ in range(10))
    await update_doctor_password(db, doctor, temp_password)
    doctor.is_initial_password = True
    await db.commit()

    return {"code": 200, "message": "임시 비밀번호가 발급되었습니다.", "result": {"temp_password": temp_password}}

# 계정 문의
@router.post("/account-inquiry")
async def account_inquiry(request: AccountInquiryRequest, db: AsyncSession = Depends(get_db)):
    doctor = await get_doctor_by_inquiry(db, request.hospital_name, request.business_number, request.license_number)

    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="등록된 정보를 찾을 수 없습니다. 입력하신 정보를 다시 확인해주세요."
        )

    if not doctor.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="등록된 이메일이 없습니다. 관리자에게 문의해주세요."
        )

    temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits + "!@#$%") for _ in range(10))
    await update_doctor_password(db, doctor, temp_password)
    doctor.is_initial_password = True
    await db.commit()

    send_account_credentials(
        doctor_email=doctor.email,
        doctor_name=doctor.doctor_name,
        hospital_name=doctor.hospital_name,
        loginid=doctor.loginid,
        temp_password=temp_password,
    )

    return {"code": 200, "message": "등록된 이메일로 계정 정보를 발송했습니다."}

# 같은 병원 소속 수의사 목록
@router.get("/hospital/doctors", status_code=200)
async def list_hospital_doctors(
    db: AsyncSession = Depends(get_db),
    current_doctor = Depends(get_current_doctor),
):
    doctors = await get_doctors_by_hospital(db, current_doctor.hospital_name)
    return {
        "code": 200,
        "result": [
            {"doctorid": d.doctorid, "doctor_name": d.doctor_name, "loginid": d.loginid}
            for d in doctors
        ],
    }
