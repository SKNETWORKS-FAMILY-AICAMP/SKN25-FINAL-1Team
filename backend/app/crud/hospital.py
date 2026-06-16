from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.hospital import Hospital
from app.models.doctor import Doctor
from app.models.hospital_profile import HospitalProfile
from app.models.doctor_profile import DoctorProfile
from app.models.vet_schedule import HospitalWeeklySchedule
from app.core.security import hash_password


async def get_hospital_by_loginid(db: AsyncSession, loginid: str):
    result = await db.execute(select(Hospital).where(Hospital.loginid == loginid))
    return result.scalar_one_or_none()


async def get_hospital_by_id(db: AsyncSession, hospitalid: int):
    return await db.get(Hospital, hospitalid)


async def get_hospital_by_credentials(db: AsyncSession, hospital_name: str, business_number: str):
    result = await db.execute(
        select(Hospital).where(
            Hospital.hospital_name == hospital_name,
            Hospital.business_number == business_number,
        )
    )
    return result.scalar_one_or_none()


async def update_hospital_password(db: AsyncSession, hospital: Hospital, new_password: str):
    hospital.password = hash_password(new_password)
    hospital.is_initial_password = False
    await db.commit()
    await db.refresh(hospital)
    return hospital


def _fmt_time(t) -> str | None:
    return t.strftime("%H:%M") if t else None


async def format_hospital_hours(db: AsyncSession, hospitalid: int) -> str | None:
    """병원 대표 진료시간 문자열. hospital_weekly_scheduleDB 기반."""
    rows = await db.execute(
        select(HospitalWeeklySchedule).where(HospitalWeeklySchedule.hospitalid == hospitalid)
    )
    by_day = {v.day_of_week: v for v in rows.scalars().all()}
    if not by_day:
        return None

    def line(label: str, day: int) -> str:
        v = by_day.get(day)
        if v and v.is_open and v.start_time and v.end_time:
            return f"{label} {_fmt_time(v.start_time)} ~ {_fmt_time(v.end_time)}"
        return f"{label} 휴진"

    # day_of_week: 0=월 … 5=토 6=일
    return "\n".join([line("평일", 0), line("토요일", 5), line("일요일", 6)])


async def get_hospital_detail(db: AsyncSession, hospitalid: int) -> dict | None:
    """보호자 병원탭 상세 (병원 + 프로필 + 원장들 + 원장 프로필 + 진료시간)."""
    hosp = await db.get(Hospital, hospitalid)
    if not hosp:
        return None
    prof = await db.get(HospitalProfile, hospitalid)

    docs = await db.execute(
        select(Doctor).where(Doctor.hospitalid == hospitalid).order_by(Doctor.doctorid)
    )
    doctors_out = []
    for d in docs.scalars().all():
        dp = await db.get(DoctorProfile, d.doctorid)
        doctors_out.append({
            "doctorid": d.doctorid,
            "name": d.doctor_name,
            "specialty": dp.specialty if dp else None,
            "education": dp.education if dp else None,
            "bio": dp.bio if dp else None,
            "specialtyAreas": (dp.specialty_areas if dp and dp.specialty_areas else []),
            "profileImage": dp.profile_image_url if dp else None,
        })

    return {
        "hospitalid": hosp.hospitalid,
        "name": hosp.hospital_name,
        "tagline": prof.tagline if prof else None,
        "intro": prof.intro if prof else None,
        "address": hosp.hospital_address,
        "phone": hosp.hospital_number,
        "hours": await format_hospital_hours(db, hospitalid),
        "bannerImage": prof.banner_image_url if prof else None,
        "features": (prof.features if prof and prof.features else []),
        "doctors": doctors_out,
    }


async def search_hospitals(db: AsyncSession, query: str = None) -> list[dict]:
    q = select(Hospital).order_by(Hospital.hospitalid)
    if query:
        q = q.where(Hospital.hospital_name.ilike(f"%{query}%"))
    result = await db.execute(q)
    return [
        {"hospitalid": h.hospitalid, "name": h.hospital_name, "address": h.hospital_address}
        for h in result.scalars().all()
    ]
