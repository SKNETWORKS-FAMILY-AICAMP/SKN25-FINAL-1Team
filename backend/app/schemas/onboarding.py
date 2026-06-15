from typing import Optional, List
from pydantic import BaseModel


class DayHours(BaseModel):
    open: str
    close: str


class LunchHours(BaseModel):
    start: str
    end: str


class OperatingHours(BaseModel):
    weekday: Optional[DayHours] = None
    saturday: Optional[DayHours] = None
    sunday: Optional[DayHours] = None
    holiday: Optional[DayHours] = None
    lunch: Optional[LunchHours] = None


class DoctorApplicationIn(BaseModel):
    name: str
    licenseNumber: str
    licenseUrl: Optional[str] = None
    email: Optional[str] = None
    specialty: Optional[str] = None
    education: Optional[str] = None
    bio: Optional[str] = None
    specialtyAreas: List[str] = []
    photoUrl: Optional[str] = None
    # Optional future override. Today company-web sends hospital-level hours;
    # vet scheduling can later split these into doctor-specific defaults.
    hours: Optional[OperatingHours] = None


class SignupRequestIn(BaseModel):
    """company-web /apply 제출 본문. 파일은 S3 업로드 후 URL 로 전달."""
    hospitalName: str
    businessNumber: str
    businessLicenseUrl: Optional[str] = None
    hospitalPhone: Optional[str] = None
    hospitalAddress: Optional[str] = None
    ownerEmail: Optional[str] = None
    desiredLoginId: str
    tagline: Optional[str] = None
    intro: Optional[str] = None
    features: List[str] = []
    bannerUrl: Optional[str] = None
    hours: Optional[OperatingHours] = None
    doctors: List[DoctorApplicationIn] = []


class SignupRequestOut(BaseModel):
    """운영진 목록/상세 응답. 저장된 신청 원본 + 메타."""
    id: int
    hospitalName: str
    businessNumber: str
    businessLicenseUrl: Optional[str] = None
    hospitalPhone: Optional[str] = None
    hospitalAddress: Optional[str] = None
    ownerEmail: Optional[str] = None
    desiredLoginId: str
    tagline: Optional[str] = None
    intro: Optional[str] = None
    features: List[str] = []
    bannerUrl: Optional[str] = None
    hours: Optional[OperatingHours] = None
    doctors: List[DoctorApplicationIn] = []
    status: str
    rejectReason: Optional[str] = None
    createdHospitalid: Optional[int] = None
    createdAt: Optional[str] = None
