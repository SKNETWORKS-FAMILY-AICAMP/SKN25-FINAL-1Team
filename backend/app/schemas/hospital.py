from typing import Optional, List
from pydantic import BaseModel


class HospitalDoctorOut(BaseModel):
    """보호자 병원탭의 원장 카드. 프론트 hospital-mock 의 HospitalDoctor 와 동일 필드명."""
    doctorid: int
    name: str
    specialty: Optional[str] = None
    education: Optional[str] = None
    bio: Optional[str] = None
    specialtyAreas: List[str] = []
    profileImage: Optional[str] = None
    profileImagePosition: Optional[str] = None


class HospitalDetailOut(BaseModel):
    """보호자 병원탭 상세. 프론트 hospital-mock 의 Hospital 과 동일 필드명."""
    hospitalid: int
    name: str
    tagline: Optional[str] = None
    intro: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    hours: Optional[str] = None  # vet_scheduleDB 에서 만든 표시 문자열(여러 줄)
    bannerImage: Optional[str] = None
    bannerImagePosition: Optional[str] = None
    features: List[str] = []
    doctors: List[HospitalDoctorOut] = []


class MyHospitalOut(BaseModel):
    """보호자가 등록한 병원 목록 항목."""
    hospitalid: int
    name: str
    is_primary: bool
    is_active: bool = True  # 폐업 병원 뱃지용


class AddHospitalRequest(BaseModel):
    hospitalid: int
