import secrets
import string
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinic_signup_request import ClinicSignupRequest
from app.models.hospital import Hospital
from app.models.hospital_profile import HospitalProfile
from app.models.doctor import Doctor
from app.models.doctor_profile import DoctorProfile
from app.schemas.onboarding import SignupRequestIn
from app.core.security import hash_password


def to_out(r: ClinicSignupRequest) -> dict:
    """ClinicSignupRequest → SignupRequestOut 호환 dict (프론트 camelCase)."""
    return {
        "id": r.id,
        "hospitalName": r.hospital_name,
        "businessNumber": r.business_number,
        "businessLicenseUrl": r.business_license_url,
        "hospitalPhone": r.hospital_phone,
        "hospitalAddress": r.hospital_address,
        "ownerEmail": r.owner_email,
        "desiredLoginId": r.desired_loginid,
        "tagline": r.tagline,
        "intro": r.intro,
        "features": r.features or [],
        "bannerUrl": r.banner_image_url,
        "hours": r.hours,
        "doctors": r.doctors or [],
        "status": r.status,
        "rejectReason": r.reject_reason,
        "createdHospitalid": r.created_hospitalid,
        "createdAt": r.created_at.isoformat() if r.created_at else None,
    }


async def create_signup_request(db: AsyncSession, data: SignupRequestIn) -> ClinicSignupRequest:
    r = ClinicSignupRequest(
        hospital_name=data.hospitalName,
        business_number=data.businessNumber,
        business_license_url=data.businessLicenseUrl,
        hospital_phone=data.hospitalPhone,
        hospital_address=data.hospitalAddress,
        owner_email=data.ownerEmail,
        desired_loginid=data.desiredLoginId,
        tagline=data.tagline,
        intro=data.intro,
        features=data.features,
        banner_image_url=data.bannerUrl,
        hours=data.hours.model_dump() if data.hours else None,
        doctors=[d.model_dump() for d in data.doctors],
        status="접수",
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


async def list_signup_requests(db: AsyncSession, status: str = None) -> list[ClinicSignupRequest]:
    q = select(ClinicSignupRequest).order_by(ClinicSignupRequest.created_at.desc())
    if status:
        q = q.where(ClinicSignupRequest.status == status)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_signup_request(db: AsyncSession, req_id: int) -> ClinicSignupRequest | None:
    return await db.get(ClinicSignupRequest, req_id)


async def reject_signup_request(db: AsyncSession, req_id: int, reason: str) -> ClinicSignupRequest | None:
    r = await db.get(ClinicSignupRequest, req_id)
    if not r:
        return None
    r.status = "반려"
    r.reject_reason = reason
    r.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(r)
    return r


def _gen_temp_password(length: int = 10) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


async def approve_signup_request(db: AsyncSession, req_id: int) -> dict | None:
    """발행: 병원+프로필+원장(들)+계정 생성. 임시비번 반환."""
    r = await db.get(ClinicSignupRequest, req_id)
    if not r or r.status == "승인발행":
        return None

    temp_password = _gen_temp_password()

    # 1) 병원 + 로그인 계정
    hospital = Hospital(
        hospital_name=r.hospital_name,
        hospital_address=r.hospital_address,
        hospital_number=r.hospital_phone,
        business_number=r.business_number,
        loginid=r.desired_loginid,
        password=hash_password(temp_password),
        is_initial_password=True,
    )
    db.add(hospital)
    await db.flush()  # hospitalid 확보

    # 2) 병원 공개 프로필
    db.add(HospitalProfile(
        hospitalid=hospital.hospitalid,
        tagline=r.tagline,
        intro=r.intro,
        banner_image_url=r.banner_image_url,
        features=r.features,
    ))

    # 3) 원장 + 공개 프로필
    for d in (r.doctors or []):
        doctor = Doctor(
            hospitalid=hospital.hospitalid,
            doctor_name=d.get("name"),
            license_number=d.get("licenseNumber"),
            email=d.get("email"),
        )
        db.add(doctor)
        await db.flush()  # doctorid 확보
        db.add(DoctorProfile(
            doctorid=doctor.doctorid,
            specialty=d.get("specialty"),
            education=d.get("education"),
            bio=d.get("bio"),
            specialty_areas=d.get("specialtyAreas") or [],
            profile_image_url=d.get("photoUrl"),
        ))
        # TODO(schedule-db-split):
        # 입점 신청의 hours 원본은 clinic_signup_requestDB.hours / doctors[].hours에 보존한다.
        # 수의사웹 스케줄 DB가 병원 기본 근무시간 / 원장별 근무시간 / 특정일 예외로
        # 분리된 뒤, app/services/schedule_provisioning.py에서 새 구조에 맞게 반영한다.
        # 현재 PR에서는 다른 팀원의 스케줄 DB 개편과 충돌하지 않도록 vet_scheduleDB write를 막아둔다.
        # provision_doctor_weekly_schedule(db, doctor.doctorid, d.get("hours") or r.hours)

    # 4) 신청 상태
    r.status = "승인발행"
    r.created_hospitalid = hospital.hospitalid
    r.reviewed_at = datetime.now(timezone.utc)
    await db.commit()

    # 5) 이메일 통보 (실패해도 발행은 성공 처리)
    if r.owner_email:
        try:
            from app.core.email import send_account_credentials
            send_account_credentials(
                doctor_email=r.owner_email,
                doctor_name=r.hospital_name,
                hospital_name=r.hospital_name,
                loginid=r.desired_loginid,
                temp_password=temp_password,
            )
        except Exception:
            pass

    return {
        "hospitalid": hospital.hospitalid,
        "loginid": r.desired_loginid,
        "temp_password": temp_password,
    }
