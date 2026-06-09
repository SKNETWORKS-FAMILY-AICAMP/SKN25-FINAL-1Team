from pydantic import BaseModel
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

# 비밀번호 재설정 요청
class DoctorPasswordResetRequest(BaseModel):
    loginid: str
    license_number: str