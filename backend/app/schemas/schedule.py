from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum

# 상태값 enum
class ScheduleStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

# 정기검진 예약 요청
class CheckupScheduleRequest(BaseModel):
    pet_id: int
    date: str
    time: str
    memo: Optional[str] = None
    category_code: int = 1  # 1=정기검진, 2=일반진료
    doctorid: Optional[int] = None   # 보호자가 선택한 원장(다병원·다원장)
    hospitalid: Optional[int] = None  # 원장 미지정 시 이 병원의 첫 활성 원장

# 챗봇 예약 확정 요청
class ConfirmScheduleRequest(BaseModel):
    emrid: int
    doctorid: int
    confirmed_time: str
    duration_min: int
    hospitalid: int | None = None  # 다중 병원: 선택된 병원(스코핑·검증용)
    pre_visit_instructions: list[str] = []  # 재진입 복원용 — 주의사항 카드 저장

# 예약 변경 요청
class UpdateScheduleRequest(BaseModel):
    confirmed_time: str
    duration_min: int

# 예약 응답
class ScheduleResponse(BaseModel):
    schedule_id: int
    pet_name: str
    category: str
    date: str
    time: str
    status: str
    memo: Optional[str] = None

# 예약 목록 카드 응답
class ScheduleCardResponse(BaseModel):
    schedule_id: int
    pet_name: str
    pet_profile_image: Optional[str] = None
    breed: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    category: Optional[str] = None
    status: str
    confirmed_time: Optional[str] = None
    confirmed_end_time: Optional[str] = None
    duration_min: Optional[int] = None
    hospital_name: Optional[str] = None
    hospital_address: Optional[str] = None
    doctorid: Optional[int] = None
    doctor_name: Optional[str] = None

# 페이지네이션
class Pagination(BaseModel):
    page: int
    size: int
    has_next: bool