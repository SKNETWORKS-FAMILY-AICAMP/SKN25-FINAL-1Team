from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import verify_password, create_access_token
from app.core.dependencies import get_current_admin
from app.crud.admin import get_admin_by_loginid
from app.crud import signup_request as sr_crud
from app.crud import admin_hospital as ah_crud
from app.crud import contact_inquiry as ci_crud
from app.schemas.admin import AdminLoginRequest, RejectRequest
from pydantic import BaseModel as _BaseModel
from app.schemas.admin_hospital import (
    HospitalProfileUpdate,
    DoctorCreate,
    DoctorProfileUpdate,
    DoctorActiveUpdate,
)
from app.api.settings import (
    WeeklyScheduleResponse,
    _get_hospital_weekly_schedule,
    _update_hospital_weekly_schedule,
)
from app.models.validation_result import ValidationResult

router = APIRouter(prefix="/admin", tags=["admin"])


# ── 로그인 ─────────────────────────────────────────────────
@router.post("/login")
async def admin_login(body: AdminLoginRequest, db: AsyncSession = Depends(get_db)):
    admin = await get_admin_by_loginid(db, body.loginid)
    if not admin or not verify_password(body.password, admin.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )
    token = create_access_token({"sub": str(admin.adminid), "type": "admin"})
    return {"code": 200, "result": {"access_token": token, "name": admin.name}}


# ── 입점 신청 검토/발행 ────────────────────────────────────
@router.get("/signup-requests")
async def list_requests(
    status: str = Query(None),
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    rows = await sr_crud.list_signup_requests(db, status)
    return {"code": 200, "result": [sr_crud.to_out(r) for r in rows]}


@router.get("/signup-requests/{req_id}")
async def get_request(
    req_id: int,
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    r = await sr_crud.get_signup_request(db, req_id)
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="신청을 찾을 수 없습니다.")
    return {"code": 200, "result": sr_crud.to_out(r)}


@router.post("/signup-requests/{req_id}/approve")
async def approve_request(
    req_id: int,
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    try:
        result = await sr_crud.approve_signup_request(db, req_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="발행할 수 없는 신청입니다(없거나 이미 발행됨).",
        )
    return {"code": 200, "result": result}


@router.post("/signup-requests/{req_id}/reject")
async def reject_request(
    req_id: int,
    body: RejectRequest,
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    r = await sr_crud.reject_signup_request(db, req_id, body.reason or "")
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="신청을 찾을 수 없습니다.")
    return {"code": 200, "result": sr_crud.to_out(r)}


# ── 병원/원장 프로필 관리 ──────────────────────────────────
@router.get("/hospitals")
async def admin_list_hospitals(
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    return {"code": 200, "result": await ah_crud.list_hospitals(db)}


@router.get("/hospitals/{hid}")
async def admin_get_hospital(
    hid: int,
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    detail = await ah_crud.get_hospital_admin(db, hid)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="병원을 찾을 수 없습니다.")
    return {"code": 200, "result": detail}


@router.put("/hospitals/{hid}/profile")
async def admin_update_hospital_profile(
    hid: int,
    body: HospitalProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    ok = await ah_crud.update_hospital_profile(db, hid, body.model_dump(exclude_unset=True))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="병원을 찾을 수 없습니다.")
    return {"code": 200, "message": "저장되었습니다."}


@router.get("/hospitals/{hid}/hours", response_model=WeeklyScheduleResponse)
async def admin_get_hospital_hours(
    hid: int,
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    return await _get_hospital_weekly_schedule(db, hid)


@router.put("/hospitals/{hid}/hours", response_model=WeeklyScheduleResponse)
async def admin_update_hospital_hours(
    hid: int,
    body: WeeklyScheduleResponse,
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    return await _update_hospital_weekly_schedule(db, hid, body.schedule)


@router.put("/hospitals/{hid}/active")
async def admin_set_hospital_active(
    hid: int,
    body: DoctorActiveUpdate,  # {is_active: bool} 동일 형태 재사용
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    ok = await ah_crud.set_hospital_active(db, hid, body.is_active)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="병원을 찾을 수 없습니다.")
    return {"code": 200, "message": "폐업 처리되었습니다." if not body.is_active else "영업 재개되었습니다."}


@router.post("/hospitals/{hid}/doctors")
async def admin_add_doctor(
    hid: int,
    body: DoctorCreate,
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    doctorid = await ah_crud.add_doctor(db, hid, body.model_dump())
    if doctorid is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="병원을 찾을 수 없습니다.")
    return {"code": 200, "result": {"doctorid": doctorid}, "message": "원장이 추가되었습니다."}


@router.put("/doctors/{did}/profile")
async def admin_update_doctor_profile(
    did: int,
    body: DoctorProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    ok = await ah_crud.update_doctor_profile(db, did, body.model_dump(exclude_unset=True))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="원장을 찾을 수 없습니다.")
    return {"code": 200, "message": "저장되었습니다."}


@router.put("/doctors/{did}/active")
async def admin_set_doctor_active(
    did: int,
    body: DoctorActiveUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    ok = await ah_crud.set_doctor_active(db, did, body.is_active)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="원장을 찾을 수 없습니다.")
    return {"code": 200, "message": "변경되었습니다."}


# ── 홈페이지 문의 관리 ─────────────────────────────────────
class ReplyRequest(_BaseModel):
    reply_message: str


@router.get("/contacts")
async def admin_list_contacts(
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    rows = await ci_crud.list_contacts(db)
    return {"code": 200, "result": [ci_crud.to_out(r) for r in rows]}


@router.get("/contacts/{contact_id}")
async def admin_get_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    row = await ci_crud.get_contact(db, contact_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="문의를 찾을 수 없습니다.")
    return {"code": 200, "result": ci_crud.to_out(row)}


@router.post("/contacts/{contact_id}/reply")
async def admin_reply_contact(
    contact_id: int,
    body: ReplyRequest,
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    row = await ci_crud.get_contact(db, contact_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="문의를 찾을 수 없습니다.")

    from app.core.email import send_contact_reply
    sent = send_contact_reply(
        to_email=row.email,
        to_name=row.name,
        original_message=row.message,
        reply_message=body.reply_message,
    )
    if not sent:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="이메일 발송에 실패했습니다.")

    await ci_crud.mark_replied(db, contact_id)
    return {"code": 200, "message": "답장이 발송되었습니다."}


# ── 모니터링: Validation (validation_resultDB) ─────────────
@router.get("/validation/results")
async def validation_results(
    attention_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    q = select(ValidationResult).order_by(ValidationResult.created_at.desc()).limit(200)
    if attention_only:
        q = q.where(ValidationResult.overall == "ATTENTION")
    rows = await db.execute(q)
    result = [
        {
            "emrid": v.emrid,
            "createdAt": v.created_at.isoformat() if v.created_at else None,
            "overall": v.overall,
            "completeness": float(v.completeness_score) if v.completeness_score is not None else None,
            "checks": v.checks or [],
            "summary": v.summary,
        }
        for v in rows.scalars().all()
    ]
    return {"code": 200, "result": result}


# ── 검증 실행 ──────────────────────────────────────────────────
@router.post("/validation/run")
async def run_validation_endpoint(
    schedule_id: int = Query(..., description="검증할 Schedule ID"),
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    from ai.agents.evaluation import run_case_evaluation
    result = await run_case_evaluation(schedule_id, db)
    return {"code": 200, "result": result}


# ── 모니터링: Judge (메모리 링버퍼 — DB 불필요) ──
@router.get("/judge/results")
async def judge_results(
    needs_review_only: bool = Query(False),
    current_admin=Depends(get_current_admin),
):
    from ai.monitoring import recent_judge
    return {"code": 200, "result": recent_judge(needs_review_only)}
