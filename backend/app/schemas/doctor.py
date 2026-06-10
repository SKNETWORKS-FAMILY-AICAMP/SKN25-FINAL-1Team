import re
from pydantic import BaseModel, field_validator
from typing import Optional

# 로그인 요청
class DoctorLoginRequest(BaseModel):
    loginid: str
    password: str

# 로그인 응답
class DoctorTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    is_initial_password: bool
    license_number: Optional[str] = None
    hospital_number: Optional[str] = None
    business_number: Optional[str] = None

# 비밀번호 변경 요청
class DoctorPasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str
    new_password_confirm: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("비밀번호는 8자 이상이어야 합니다.")
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("비밀번호에 영문자가 포함되어야 합니다.")
        if not re.search(r"\d", v):
            raise ValueError("비밀번호에 숫자가 포함되어야 합니다.")
        if not re.search(r"[^A-Za-z\d]", v):
            raise ValueError("비밀번호에 특수문자가 포함되어야 합니다.")
        return v

# 비밀번호 재설정 요청
class DoctorPasswordResetRequest(BaseModel):
    loginid: str
    license_number: str

# 계정 문의 요청
class AccountInquiryRequest(BaseModel):
    hospital_name: str
    business_number: str
    license_number: str