from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.onboarding import SignupRequestIn
from app.crud import signup_request as sr_crud
from app.utils.s3 import create_presigned_put

router = APIRouter(tags=["signup-requests"])

ALLOWED_PREFIXES = {"hospital", "doctor", "signup-docs"}


# 입점 신청 (공개 — company-web /apply)
@router.post("/signup-requests")
async def create_signup(body: SignupRequestIn, db: AsyncSession = Depends(get_db)):
    r = await sr_crud.create_signup_request(db, body)
    return {"code": 200, "result": {"id": r.id, "status": r.status}}


# 업로드 presign (공개 — 신청 폼에서 배너/사진/서류 직접 업로드)
@router.get("/uploads/presigned-url")
async def presigned_url(
    file_name: str = Query(...),
    content_type: str = Query(...),
    prefix: str = Query("signup-docs"),
):
    if prefix not in ALLOWED_PREFIXES:
        prefix = "signup-docs"
    return {"code": 200, "result": create_presigned_put(file_name, content_type, prefix=prefix)}
