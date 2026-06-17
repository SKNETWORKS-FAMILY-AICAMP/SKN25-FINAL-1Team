"""수의사 병원 관리 — 병원/원장 프로필 CRUD.

토큰에서 추출한 hospitalid를 기준으로 자기 병원 정보만 수정할 수 있다.
의사 수정 시 해당 doctorid가 같은 병원 소속인지 검증한다.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hospital import Hospital
from app.models.hospital_profile import HospitalProfile
from app.models.doctor import Doctor
from app.models.doctor_profile import DoctorProfile


async def get_vet_hospital_profile(db: AsyncSession, hid: int) -> dict | None:
    h = await db.get(Hospital, hid)
    if not h:
        return None
    prof = await db.get(HospitalProfile, hid)

    docs = await db.execute(
        select(Doctor)
        .where(Doctor.hospitalid == hid, Doctor.is_active == True)
        .order_by(Doctor.doctorid)
    )
    doctors = []
    for d in docs.scalars().all():
        dp = await db.get(DoctorProfile, d.doctorid)
        doctors.append({
            "doctorid": d.doctorid,
            "name": d.doctor_name,
            "licenseNumber": d.license_number,
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
        "tagline": prof.tagline if prof else None,
        "intro": prof.intro if prof else None,
        "bannerImage": prof.banner_image_url if prof else None,
        "bannerImagePosition": prof.banner_image_position if prof else None,
        "features": (prof.features if prof and prof.features else []),
        "doctors": doctors,
    }


async def update_vet_hospital_profile(db: AsyncSession, hid: int, data: dict) -> bool:
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


async def get_vet_doctors(db: AsyncSession, hid: int) -> list[dict]:
    docs = await db.execute(
        select(Doctor)
        .where(Doctor.hospitalid == hid, Doctor.is_active == True)
        .order_by(Doctor.doctorid)
    )
    result = []
    for d in docs.scalars().all():
        dp = await db.get(DoctorProfile, d.doctorid)
        result.append({
            "doctorid": d.doctorid,
            "name": d.doctor_name,
            "licenseNumber": d.license_number,
            "specialty": dp.specialty if dp else None,
            "education": dp.education if dp else None,
            "bio": dp.bio if dp else None,
            "specialtyAreas": (dp.specialty_areas if dp and dp.specialty_areas else []),
            "profileImage": dp.profile_image_url if dp else None,
            "profileImagePosition": dp.profile_image_position if dp else None,
        })
    return result


async def deactivate_vet_doctor(db: AsyncSession, hid: int, did: int) -> bool:
    d = await db.get(Doctor, did)
    if not d or d.hospitalid != hid:
        return False
    d.is_active = False
    await db.commit()
    return True


async def create_vet_doctor(db: AsyncSession, hid: int, name: str) -> dict:
    d = Doctor(hospitalid=hid, doctor_name=name, is_active=True)
    db.add(d)
    await db.flush()
    dp = DoctorProfile(doctorid=d.doctorid)
    db.add(dp)
    await db.commit()
    return {
        "doctorid": d.doctorid,
        "name": d.doctor_name,
        "specialty": None,
        "education": None,
        "bio": None,
        "specialtyAreas": [],
        "profileImage": None,
        "profileImagePosition": None,
    }


async def update_vet_doctor_profile(
    db: AsyncSession, hid: int, did: int, data: dict
) -> bool:
    d = await db.get(Doctor, did)
    if not d or d.hospitalid != hid:
        return False

    if data.get("name") is not None:
        d.doctor_name = data["name"]
    if "licenseNumber" in data:
        d.license_number = data["licenseNumber"]

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
