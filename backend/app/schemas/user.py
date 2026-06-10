import re
from typing import Optional
from pydantic import BaseModel, model_validator, field_validator

# 회원가입 요청
class UserCreate(BaseModel):
    name: str
    loginid: str
    password: str
    password_confirm: str
    phone: str

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_confirm:
            raise ValueError("비밀번호가 일치하지 않습니다.")
        return self

# 회원가입 응답
class UserResponse(BaseModel):
    userid: int
    loginid: str
    name: str
    phone: str

    class Config:
        from_attributes = True

# 내 프로필 조회 응답
class UserProfileResponse(BaseModel):
    name: str
    phone: str
    created_at: str

# 프로필 수정 요청
class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None

# 비밀번호 변경 요청
class ChangePasswordRequest(BaseModel):
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
