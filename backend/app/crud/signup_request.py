import secrets
import string
from datetime import datetime, time, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinic_signup_request import ClinicSignupRequest
from app.models.hospital import Hospital
from app.models.hospital_profile import HospitalProfile
from app.models.doctor import Doctor
from app.models.doctor_profile import DoctorProfile
from app.models.vet_schedule import HospitalWeeklySchedule, VetWeeklySchedule
from app.schemas.onboarding import SignupRequestIn
from app.core.security import hash_password
from app.crud.hospital import get_hospital_by_loginid


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


_HOURS_KEY_TO_DAYS = {
    "weekday":  [0, 1, 2, 3, 4],
    "saturday": [5],
    "sunday":   [6],
}


def _parse_time(t: str) -> time | None:
    if not t:
        return None
    h, m = map(int, t.split(":"))
    return time(h, m)


def _build_schedule_rows(hours_dict: dict) -> list[dict]:
    lunch = hours_dict.get("lunch") or {}
    lunch_start = _parse_time(lunch.get("start"))
    lunch_end   = _parse_time(lunch.get("end"))
    rows = []
    for key, days in _HOURS_KEY_TO_DAYS.items():
        day_hours = hours_dict.get(key)
        is_open   = day_hours is not None
        start = _parse_time(day_hours["open"])  if is_open else None
        end   = _parse_time(day_hours["close"]) if is_open else None
        for dow in days:
            rows.append({
                "day_of_week": dow,
                "is_open":     is_open,
                "start_time":  start,
                "end_time":    end,
                "lunch_start": lunch_start if is_open else None,
                "lunch_end":   lunch_end   if is_open else None,
            })
    return rows


def _gen_temp_password(length: int = 10) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


async def approve_signup_request(db: AsyncSession, req_id: int) -> dict | None:
    """발행: 병원+프로필+원장(들)+계정 생성. 임시비번 반환."""
    r = await db.get(ClinicSignupRequest, req_id)
    if not r or r.status == "승인발행":
        return None

    temp_password = _gen_temp_password()

    # 1) loginid 중복 사전 체크
    if await get_hospital_by_loginid(db, r.desired_loginid):
        raise ValueError(f"이미 사용 중인 로그인 아이디입니다: {r.desired_loginid}")

    # 1) 병원 + 로그인 계정
    hospital = Hospital(
        hospital_name=r.hospital_name,
        hospital_address=r.hospital_address,
        hospital_number=r.hospital_phone,
        business_number=r.business_number,
        owner_email=r.owner_email,
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

    # 2-1) 병원 주간 스케줄
    if r.hours:
        for row in _build_schedule_rows(r.hours):
            db.add(HospitalWeeklySchedule(hospitalid=hospital.hospitalid, **row))

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
        # 3-1) 수의사 주간 스케줄 (의사 개별 hours 우선, 없으면 병원 hours 폴백)
        doc_hours = d.get("hours") or r.hours
        if doc_hours:
            for row in _build_schedule_rows(doc_hours):
                db.add(VetWeeklySchedule(doctorid=doctor.doctorid, **row))

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
