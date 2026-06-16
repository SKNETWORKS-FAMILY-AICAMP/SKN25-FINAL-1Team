from typing import Optional, List
from pydantic import BaseModel


class HospitalProfileUpdate(BaseModel):
    """운영자 병원 프로필 수정. 주어진 필드만 갱신(exclude_unset)."""
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    tagline: Optional[str] = None
    intro: Optional[str] = None
    bannerImage: Optional[str] = None
    bannerImagePosition: Optional[str] = None  # CSS object-position "x% y%"
    features: Optional[List[str]] = None


class DoctorCreate(BaseModel):
    """운영자 원장 추가 (계정 발급 없음 — Doctor + DoctorProfile 레코드만)."""
    name: str
    licenseNumber: Optional[str] = None
    email: Optional[str] = None
    specialty: Optional[str] = None
    education: Optional[str] = None
    bio: Optional[str] = None
    specialtyAreas: List[str] = []
    profileImage: Optional[str] = None
    profileImagePosition: Optional[str] = None


class DoctorProfileUpdate(BaseModel):
    """운영자 원장 프로필 수정. 주어진 필드만 갱신(exclude_unset)."""
    name: Optional[str] = None
    licenseNumber: Optional[str] = None
    email: Optional[str] = None
    specialty: Optional[str] = None
    education: Optional[str] = None
    bio: Optional[str] = None
    specialtyAreas: Optional[List[str]] = None
    profileImage: Optional[str] = None
    profileImagePosition: Optional[str] = None


class DoctorActiveUpdate(BaseModel):
    is_active: bool
