"""운영자 백오피스 — 병원/원장 프로필 관리 CRUD.

병원 공개 프로필(HospitalProfile)·원장 공개 프로필(DoctorProfile)을 승인 후에도
운영팀이 수정/추가/비활성할 수 있게 한다. 입점 발행([crud/signup_request.approve])과
동일한 생성 패턴을 재사용한다.
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hospital import Hospital
from app.models.hospital_profile import HospitalProfile
from app.models.doctor import Doctor
from app.models.doctor_profile import DoctorProfile


async def list_hospitals(db: AsyncSession) -> list[dict]:
    rows = await db.execute(select(Hospital).order_by(Hospital.hospitalid))
    hospitals = rows.scalars().all()
    out = []
    for h in hospitals:
        count = (
            await db.execute(
                select(func.count())
                .select_from(Doctor)
                .where(Doctor.hospitalid == h.hospitalid)
            )
        ).scalar_one()
        out.append({
            "hospitalid": h.hospitalid,
            "name": h.hospital_name,
            "address": h.hospital_address,
            "phone": h.hospital_number,
            "doctorCount": count,
            "is_active": h.is_active,
        })
    return out


async def get_hospital_admin(db: AsyncSession, hid: int) -> dict | None:
    """운영자 편집용 상세 — 비활성 원장도 포함(운영팀은 모두 봐야 함)."""
    h = await db.get(Hospital, hid)
    if not h:
        return None
    prof = await db.get(HospitalProfile, hid)

    docs = await db.execute(
        select(Doctor).where(Doctor.hospitalid == hid).order_by(Doctor.doctorid)
    )
    doctors = []
    for d in docs.scalars().all():
        dp = await db.get(DoctorProfile, d.doctorid)
        doctors.append({
            "doctorid": d.doctorid,
            "name": d.doctor_name,
            "licenseNumber": d.license_number,
            "email": d.email,
            "is_active": d.is_active,
            "specialty": dp.specialty if dp else None,
            "education": dp.education if dp else None,
            "bio": dp.bio if dp else None,
            "specialtyAreas": (dp.specialty_areas if dp and dp.specialty_areas else []),
            "profileImage": dp.profile_image_url if dp else None,
            "profileImagePosition": dp.profile_image_position if dp else None,
        })

    return {
        "hospitalid": h.hospitalid,
        "name": h.hospital_name,
        "address": h.hospital_address,
        "phone": h.hospital_number,
        "businessNumber": h.business_number,
        "is_active": h.is_active,
        "tagline": prof.tagline if prof else None,
        "intro": prof.intro if prof else None,
        "bannerImage": prof.banner_image_url if prof else None,
        "bannerImagePosition": prof.banner_image_position if prof else None,
        "features": (prof.features if prof and prof.features else []),
        "doctors": doctors,
    }


async def update_hospital_profile(db: AsyncSession, hid: int, data: dict) -> bool:
    h = await db.get(Hospital, hid)
    if not h:
        return False
    if data.get("name") is not None:
        h.hospital_name = data["name"]
    if "address" in data:
        h.hospital_address = data["address"]
    if "phone" in data:
        h.hospital_number = data["phone"]

    prof = await db.get(HospitalProfile, hid)
    if not prof:
        prof = HospitalProfile(hospitalid=hid)
        db.add(prof)
    if "tagline" in data:
        prof.tagline = data["tagline"]
    if "intro" in data:
        prof.intro = data["intro"]
    if "bannerImage" in data:
        prof.banner_image_url = data["bannerImage"]
    if "bannerImagePosition" in data:
        prof.banner_image_position = data["bannerImagePosition"]
    if "features" in data:
        prof.features = data["features"]

    await db.commit()
    return True


async def add_doctor(db: AsyncSession, hid: int, data: dict) -> int | None:
    h = await db.get(Hospital, hid)
    if not h:
        return None
    doctor = Doctor(
        hospitalid=hid,
        doctor_name=data["name"],
        license_number=data.get("licenseNumber"),
        email=data.get("email"),
    )
    db.add(doctor)
    await db.flush()  # doctorid 확보
    db.add(DoctorProfile(
        doctorid=doctor.doctorid,
        specialty=data.get("specialty"),
        education=data.get("education"),
        bio=data.get("bio"),
        specialty_areas=data.get("specialtyAreas") or [],
        profile_image_url=data.get("profileImage"),
        profile_image_position=data.get("profileImagePosition"),
    ))
    await db.commit()
    return doctor.doctorid


async def update_doctor_profile(db: AsyncSession, did: int, data: dict) -> bool:
    d = await db.get(Doctor, did)
    if not d:
        return False
    if data.get("name") is not None:
        d.doctor_name = data["name"]
    if "licenseNumber" in data:
        d.license_number = data["licenseNumber"]
    if "email" in data:
        d.email = data["email"]

    dp = await db.get(DoctorProfile, did)
    if not dp:
        dp = DoctorProfile(doctorid=did)
        db.add(dp)
    if "specialty" in data:
        dp.specialty = data["specialty"]
    if "education" in data:
        dp.education = data["education"]
    if "bio" in data:
        dp.bio = data["bio"]
    if "specialtyAreas" in data:
        dp.specialty_areas = data["specialtyAreas"]
    if "profileImage" in data:
        dp.profile_image_url = data["profileImage"]
    if "profileImagePosition" in data:
        dp.profile_image_position = data["profileImagePosition"]

    await db.commit()
    return True


async def set_hospital_active(db: AsyncSession, hid: int, is_active: bool) -> bool:
    """병원 폐업/영업재개. 레코드·기록은 보존하고 노출/예약 가능 여부만 토글."""
    h = await db.get(Hospital, hid)
    if not h:
        return False
    h.is_active = is_active
    await db.commit()
    return True


async def set_doctor_active(db: AsyncSession, did: int, is_active: bool) -> bool:
    d = await db.get(Doctor, did)
    if not d:
        return False
    d.is_active = is_active
    await db.commit()
    return True
