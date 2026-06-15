from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import verify_password, create_access_token
from app.core.dependencies import get_current_admin
from app.crud.admin import get_admin_by_loginid
from app.crud import signup_request as sr_crud
from app.schemas.admin import AdminLoginRequest, RejectRequest
from app.models.validation_result import ValidationResult
from app.models.agent_pipeline_result import AgentPipelineResult

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
    result = await sr_crud.approve_signup_request(db, req_id)
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


# ── 모니터링: Judge (agent_pipeline_resultDB.judge_result) ──
@router.get("/judge/results")
async def judge_results(
    needs_review_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    q = (
        select(AgentPipelineResult)
        .where(AgentPipelineResult.judge_result.isnot(None))
        .order_by(AgentPipelineResult.created_at.desc())
        .limit(200)
    )
    rows = await db.execute(q)
    result = []
    for a in rows.scalars().all():
        jr = a.judge_result or {}
        verdict = jr.get("monitoring_verdict")
        if needs_review_only and verdict != "NEEDS_REVIEW":
            continue
        result.append({
            "emrid": a.emrid,
            "createdAt": a.created_at.isoformat() if a.created_at else None,
            "verdict": verdict,
            "scores": jr.get("quality_scores") or {},
            "turnCount": jr.get("turn_count"),
            "notes": jr.get("notes"),
        })
    return {"code": 200, "result": result}
