from typing import Optional
from pydantic import BaseModel


class AdminLoginRequest(BaseModel):
    loginid: str
    password: str


class RejectRequest(BaseModel):
    reason: Optional[str] = None
