from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.onboarding import SignupRequestIn
from app.crud import signup_request as sr_crud
from app.utils.rate_limit import rate_limit
from app.utils.s3 import create_presigned_put

router = APIRouter(tags=["signup-requests"])

ALLOWED_PREFIXES = {"hospital", "doctor", "signup-docs"}
# 공개(무인증) 엔드포인트이므로 임의 파일 업로드를 막기 위해 콘텐츠 타입을 제한한다.
# 입점 신청 폼은 배너/원장 사진(이미지) + 사업자등록증/면허증(이미지·PDF)만 올린다.
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


# 입점 신청 (공개 — company-web /apply)
@router.post("/signup-requests")
async def create_signup(request: Request, body: SignupRequestIn, db: AsyncSession = Depends(get_db)):
    # 공개 엔드포인트 남용 방지: IP당 1분 5건.
    rate_limit(request, key="signup", limit=5, window_sec=60)
    r = await sr_crud.create_signup_request(db, body)
    return {"code": 200, "result": {"id": r.id, "status": r.status}}


# 업로드 presign (공개 — 신청 폼에서 배너/사진/서류 직접 업로드)
@router.get("/uploads/presigned-url")
async def presigned_url(
    request: Request,
    file_name: str = Query(...),
    content_type: str = Query(...),
    prefix: str = Query("signup-docs"),
):
    # 공개 발급이라 남용 방지: IP당 1분 20건(폼 1회에 배너/원장사진/서류 여러 장 업로드 대비).
    rate_limit(request, key="presign", limit=20, window_sec=60)
    if prefix not in ALLOWED_PREFIXES:
        prefix = "signup-docs"
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="허용되지 않은 파일 형식입니다. (이미지 또는 PDF만 가능)")
    return {"code": 200, "result": create_presigned_put(file_name, content_type, prefix=prefix)}
