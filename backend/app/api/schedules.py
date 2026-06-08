from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import logging
import uuid
from datetime import datetime, date as date_type, timezone, timedelta
from app.db.session import get_db
from app.schemas.schedule import CheckupScheduleRequest, ConfirmScheduleRequest, UpdateScheduleRequest
from app.crud.schedule import (
    create_checkup_schedule, get_schedules_by_userid,
    get_schedule_by_id, cancel_schedule,
    update_schedule_time, get_available_slots, confirm_schedule,
    get_emrid_owner_userid,
)
from app.core.dependencies import get_current_user
from app.models.pet import Pet
from app.models.doctor import Doctor
from app.models.guardian import Guardian
from app.models.triage_result import TriageResult
from ai.tasks import RUNNERS, _task_store, save_result, cleanup_task_after_ttl, safe_create_task, PipelineState
from app.crud.alarm import create_alarm

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("medipaw.audit")
from app.models.schedule import Schedule

router = APIRouter(prefix="/schedules", tags=["schedules"])

KST = timezone(timedelta(hours=9))

# Judge(LLM-as-a-Judge) QA 샘플링 비율: emrid % N == 0 일 때만 실행해 비용을 제어한다.
# 매 예약마다 돌리려면 1로 설정.
JUDGE_SAMPLE_RATE = 5



# 정기검진 예약
@router.post("/checkup", status_code=201)
async def create_checkup(
    request: CheckupScheduleRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 반려동물 확인
    result = await db.execute(
        select(Pet).where(
            Pet.petid == request.pet_id,
            Pet.userid == current_user.userid
        )
    )
    pet = result.scalar_one_or_none()
    if not pet:
        raise HTTPException(status_code=404, detail="반려동물 정보를 찾을 수 없습니다.")

    # 미래 예약 중복 확인 (과거 예약은 허용)
    dup_result = await db.execute(
        select(Schedule)
        .join(Guardian, Schedule.emrid == Guardian.emrid)
        .where(
            Guardian.petid == request.pet_id,
            Schedule.status == "CONFIRMED",
            Schedule.deleted_at.is_(None),
            Schedule.confirmed_time > datetime.now(),
        )
    )
    if dup_result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="해당 반려동물의 예약이 이미 존재합니다.")

    # 수의사 확인 (첫 번째 수의사로 자동 배정)
    result = await db.execute(select(Doctor))
    doctor = result.scalars().first()
    if not doctor:
        raise HTTPException(status_code=404, detail="등록된 수의사가 없습니다.")

    schedule, guardian = await create_checkup_schedule(
        db=db,
        pet_id=request.pet_id,
        date=request.date,
        time=request.time,
        memo=request.memo,
        doctorid=doctor.doctorid
    )

    if schedule is None:
        raise HTTPException(status_code=409, detail="선택하신 시간에 이미 예약이 있습니다.")

    # 수의사 알람 생성
    try:
        await create_alarm(
            db=db,
            doctor_id=doctor.doctorid,
            schedule_id=schedule.scheduleid,
            alarm_type="reservation_confirmed",
            contents=f"{pet.petname} 보호자가 정기검진 예약을 확정했습니다. ({request.date} {request.time})",
        )
    except Exception as e:
        logger.warning(f"[Alarm] create failed schedule_id={schedule.scheduleid}: {e}")

    return {
        "code": 201,
        "message": "예약이 완료되었습니다.",
        "result": {
            "schedule_id": schedule.scheduleid,
            "pet_name": pet.petname,
            "category": "정기검진",
            "date": request.date,
            "time": request.time,
            "memo": request.memo,
            "status": schedule.status
        }
    }


# 예약 목록 조회
@router.get("")
async def get_schedules(
    filter: str = Query("all"),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    rows, has_next = await get_schedules_by_userid(db, current_user.userid, page, size, filter)

    from datetime import date
    result = []
    for schedule, pet, doctor, category in rows:
        age = None
        if pet.birth_date:
            today = date.today()
            age = today.year - pet.birth_date.year

        raw_status = "CANCELLED" if schedule.deleted_at else schedule.status
        result.append({
            "schedule_id": schedule.scheduleid,
            "pet_id": pet.petid,
            "pet_name": pet.petname,
            "pet_profile_image": pet.profile_image,
            "breed": pet.breed,
            "age": age,
            "gender": pet.gender,
            "category": category.label if category else None,
            "status": raw_status,
            "confirmed_time": schedule.confirmed_time.astimezone(KST).isoformat() if schedule.confirmed_time else None,
            "confirmed_end_time": schedule.confirmed_end_time.astimezone(KST).isoformat() if schedule.confirmed_end_time else None,
            "duration_min": schedule.duration_min,
            "hospital_name": doctor.hospital_name if doctor else None,
            "hospital_address": doctor.hospital_address if doctor else None,
            "doctorid": schedule.doctorid,
            "doctor_name": doctor.doctor_name if doctor else None,
        })

    return {
        "code": 200,
        "result": {
            "items": result,
            "page": page,
            "has_next": has_next
        }
    }


# 빈 슬롯 조회
@router.get("/available")
async def get_available(
    date: str = Query(...),
    duration_min: int = Query(...),
    doctorid: int = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    slots = await get_available_slots(db, date, duration_min, doctorid)

    return {
        "code": 200,
        "result": [
            {
                "start_time": slot.start_time,
                "end_time": slot.end_time,
                "doctorid": slot.doctorid,
                "doctor_name": slot.doctor_name,
            }
            for slot in slots
        ]
    }


# 예약 조회
@router.get("/{schedule_id}", status_code=200)
async def get_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    schedule = await get_schedule_by_id(db, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="예약 정보를 찾을 수 없습니다.")

    guardian_result = await db.execute(
        select(Guardian).where(Guardian.emrid == schedule.emrid)
    )
    guardian = guardian_result.scalar_one_or_none()

    pet_result = await db.execute(
        select(Pet).where(Pet.petid == guardian.petid)
    )
    pet = pet_result.scalar_one_or_none()

    # 소유권 검증: 본인 반려동물의 예약만 조회 가능
    if not pet or pet.userid != current_user.userid:
        raise HTTPException(status_code=404, detail="예약 정보를 찾을 수 없습니다.")

    doctor_result = await db.execute(
        select(Doctor).where(Doctor.doctorid == schedule.doctorid)
    )
    doctor = doctor_result.scalar_one_or_none()

    from datetime import date
    age = None
    if pet.birth_date:
        today = date.today()
        age = today.year - pet.birth_date.year

    return {
        "code": 200,
        "result": {
            "schedule_id": schedule.scheduleid,
            "pet_name": pet.petname,
            "pet_profile_image": pet.profile_image,
            "breed": pet.breed,
            "age": age,
            "gender": pet.gender,
            "status": schedule.status,
            "confirmed_time": schedule.confirmed_time.astimezone(KST).isoformat() if schedule.confirmed_time else None,
            "confirmed_end_time": schedule.confirmed_end_time.astimezone(KST).isoformat() if schedule.confirmed_end_time else None,
            "duration_min": schedule.duration_min,
            "hospital_name": doctor.hospital_name if doctor else None,
            "hospital_address": doctor.hospital_address if doctor else None,
            "doctorid": schedule.doctorid,
            "doctor_name": doctor.doctor_name if doctor else None,
            "memo": guardian.memo
        }
    }


# 예약 취소 (soft cancel)
@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    schedule = await get_schedule_by_id(db, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="예약 정보를 찾을 수 없습니다.")

    # 소유권 검증: 본인 예약만 취소 가능
    owner_id = await get_emrid_owner_userid(db, schedule.emrid)
    if owner_id != current_user.userid:
        raise HTTPException(status_code=404, detail="예약 정보를 찾을 수 없습니다.")

    if schedule.status == "COMPLETED":
        raise HTTPException(status_code=400, detail="이미 완료된 예약은 취소할 수 없습니다.")

    if schedule.status == "CANCELLED":
        raise HTTPException(status_code=400, detail="이미 취소된 예약입니다.")

    if schedule.confirmed_time.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="이미 지난 예약은 취소할 수 없습니다.")

    await cancel_schedule(db, schedule)
    return {"code": 200, "message": "예약이 취소되었습니다."}


# 예약 변경
@router.patch("/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    request: UpdateScheduleRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    schedule = await get_schedule_by_id(db, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="예약 정보를 찾을 수 없습니다.")

    # 소유권 검증: 본인 예약만 변경 가능
    owner_id = await get_emrid_owner_userid(db, schedule.emrid)
    if owner_id != current_user.userid:
        raise HTTPException(status_code=404, detail="예약 정보를 찾을 수 없습니다.")

    if schedule.status in ["COMPLETED", "CANCELLED"]:
        raise HTTPException(status_code=400, detail="변경할 수 없는 예약입니다.")

    if schedule.confirmed_time.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="이미 지난 예약은 변경할 수 없습니다.")

    result = await update_schedule_time(db, schedule, request.confirmed_time, schedule.duration_min)

    if not result:
        raise HTTPException(status_code=409, detail="선택하신 시간에 이미 예약이 있습니다.")

    return {"code": 200, "message": "예약이 변경되었습니다."}


async def _run_post_booking_agents(
    emrid: int,
    scheduleid: int,
    duration_min: int,
    user_id: int,
    chart_task_id: str,
    validation_task_id: str,
    judge_task_id: str,
) -> None:
    """예약 확정 직후 asyncio.create_task로 실행되는 Chart+Validation+Judge 파이프라인."""
    from app.db.session import AsyncSessionLocal

    logger.info(f"[PostBooking] start emrid={emrid} scheduleid={scheduleid}")

    # DB에서 Triage 결과 및 Pet 정보 조회
    async with AsyncSessionLocal() as db:
        triage_row = await db.execute(select(TriageResult).where(TriageResult.emrid == emrid))
        triage = triage_row.scalar_one_or_none()
        guardian_row = await db.execute(select(Guardian).where(Guardian.emrid == emrid))
        guardian = guardian_row.scalar_one_or_none()
        pet_row = await db.execute(select(Pet).where(Pet.petid == guardian.petid)) if guardian else None
        pet = pet_row.scalar_one_or_none() if pet_row else None

    if not triage or not pet:
        logger.warning(f"[PostBooking] 필수 데이터 없음 emrid={emrid} triage={bool(triage)} pet={bool(pet)}")
        for tid in (chart_task_id, validation_task_id, judge_task_id):
            _task_store[tid] = {"status": "error", "detail": "트리아지 또는 반려동물 정보 없음"}
        return

    age = (date_type.today().year - pet.birth_date.year) if pet.birth_date else None
    pet_payload = {
        "name": pet.petname,
        "species": pet.species or "dog",
        "breed": pet.breed or "알 수 없음",
        "age": age,
        "gender": pet.gender,
        "weight": float(pet.weight_kg) if pet.weight_kg else None,
    }

    from app.crud.patient import build_patient_context
    async with AsyncSessionLocal() as db:
        patient_context_data = await build_patient_context(db, pet.petid)

    # 초진/재진 판정: 과거 완료된 EMR 이력이 있으면 재진, 없으면 초진.
    # (하드코딩 대신 실제 emr_history 유무로 계산 → chart/validation 정확도 확보)
    emr_history = patient_context_data.get("patient_context", {}).get("emr_history") or []
    is_initial_visit = len(emr_history) == 0

    triage_info = {
        "urgency_level": triage.urgency_level,
        "urgency_level_num": triage.urgency_level_num,
        "vtl_basis": triage.vtl_basis,
        "red_flags": triage.red_flags or [],
        "chief_complaint": triage.chief_complaint,
        "symptom_onset": triage.symptom_onset,
        "symptom_keywords": triage.symptom_keywords or [],
        "suspected_diseases": triage.suspected_diseases or [],
        "symptom_summary": triage.symptom_summary,
        "recommended_action": triage.recommended_action,
        "is_initial_visit": is_initial_visit,
    }

    # VTL urgency → slot_window 매핑 (Schedule Agent와 동일한 기준)
    _URGENCY_WINDOW_MAP = {
        1: "immediate", 2: "emergency_today", 3: "urgent_24h",
        4: "semi_urgent_48h", 5: "routine_72h",
    }
    actual_slot_window = _URGENCY_WINDOW_MAP.get(
        triage_info.get("urgency_level_num", 3), "urgent_24h"
    )
    schedule_slot = {
        "estimated_duration_min": duration_min,
        "is_initial_visit": is_initial_visit,
        "slot_window": actual_slot_window,
    }

    # 공용 RAG 지식 레이어: 트리/freeform 무관하게 triage 결과로 유사 상담사례를 모아
    # chart agent에 감별진단 근거로 주입한다. 실패해도 파이프라인을 막지 않는다(보조 힌트).
    chart_rag_context: list[dict] = []
    try:
        from app.services.triage_rag import search_similar_triage_cases

        rag_query = " ".join(filter(None, [
            triage_info.get("chief_complaint") or "",
            " ".join(triage_info.get("symptom_keywords") or []),
            triage_info.get("symptom_summary") or "",
        ])).strip()
        if rag_query:
            async with AsyncSessionLocal() as db_rag:
                matches = await search_similar_triage_cases(db_rag, rag_query, top_k=3)
            chart_rag_context = [m.to_dict() for m in matches if m.similarity >= 0.60]
            logger.info(
                "[PostBooking] chart RAG emrid=%s query=%r usable=%d/%d",
                emrid, rag_query[:60], len(chart_rag_context), len(matches),
            )
    except Exception as exc:
        logger.warning(f"[PostBooking] chart RAG skipped emrid={emrid}: {exc}")

    chart_payload = {
        "pet": pet_payload,
        "triage_result": triage_info,
        "triage_info": triage_info,
        "patient_context": patient_context_data,
        "schedule_slot": schedule_slot,
        "schedule_result": schedule_slot,
        "rag_context": chart_rag_context,
    }
    validation_payload = {
        "pet": pet_payload,
        "triage_result": triage_info,
        "triage_info": triage_info,
        "patient_context": patient_context_data,
        "schedule_slot": schedule_slot,
        "schedule_result": schedule_slot,
    }
    # Fetch actual chat history for chart/judge context.
    agent_chat_history: list = []
    try:
        from app.models.chat_history import ChatHistory
        async with AsyncSessionLocal() as db_j:
            ch_row = await db_j.execute(
                select(ChatHistory).where(ChatHistory.emrid == emrid)
            )
            ch = ch_row.scalar_one_or_none()
            if ch and ch.messages:
                agent_chat_history = [
                    m for m in ch.messages
                    if m.get("role") in ("user", "assistant") and m.get("content")
                ]
    except Exception as _exc:
        logger.warning(f"[PostBooking] chat_history fetch failed emrid={emrid}: {_exc}")

    chart_payload["chat_history"] = agent_chat_history

    def make_updater(tid: str):
        def update_step(step: str) -> None:
            _task_store[tid]["step"] = step
        return update_step

    # 순차 실행: Chart → Validation(차트 전달) → Judge.
    # Validation B(문진-차트 일관성)가 차트 초안을 비교하려면 차트가 먼저 완성돼야 한다.
    # 각 단계는 try/except로 격리해 한 단계 실패가 다음 단계를 막지 않게 한다.
    # (모두 예약 확정 응답 이후 백그라운드 실행이므로 보호자 대기시간엔 영향 없음.)

    # 1) Chart
    _task_store[chart_task_id] = {"status": "running", "step": "차트 초안 생성 중..."}
    chart_result = None
    try:
        chart_result = await RUNNERS["chart"](chart_payload, make_updater(chart_task_id), emrid, scheduleid)
        _task_store[chart_task_id] = {"status": "done", "result": chart_result}
        await save_result("chart", chart_result, emrid, scheduleid, user_id)
        logger.info(f"[PostBooking] chart done emrid={emrid}")
    except Exception as e:
        logger.error(f"[PostBooking] chart failed emrid={emrid}: {e}", exc_info=True)
        _task_store[chart_task_id] = {"status": "error", "detail": str(e)}
        chart_result = None

    # 2) Validation — 차트 초안을 함께 전달(B. 워크플로우 일관성 점검용)
    _task_store[validation_task_id] = {"status": "running", "step": "품질·안전성 검증 중..."}
    validation_payload["chart_result"] = chart_result
    try:
        validation_result = await RUNNERS["validation"](validation_payload, make_updater(validation_task_id), emrid, scheduleid)
        _task_store[validation_task_id] = {"status": "done", "result": validation_result}
        await save_result("validation", validation_result, emrid, scheduleid, user_id)
        logger.info(f"[PostBooking] validation done emrid={emrid} overall={validation_result.get('overall')}")
    except Exception as e:
        logger.error(f"[PostBooking] validation failed emrid={emrid}: {e}", exc_info=True)
        _task_store[validation_task_id] = {"status": "error", "detail": str(e)}

    # 3) Judge — 운영 품질 모니터링(환자 안전 검증 아님). 샘플링 + audit log만(DB 저장 없음).
    judge_payload = {
        "triage_result": triage_info,
        "triage_info": triage_info,
        "chat_history": agent_chat_history if emrid is not None and emrid % JUDGE_SAMPLE_RATE == 0 else [],
    }
    if emrid is not None and emrid % JUDGE_SAMPLE_RATE == 0:
        try:
            judge_result = await RUNNERS["judge"](judge_payload, lambda _: None, emrid, scheduleid)
            audit_logger.info(
                "[JudgeAudit] emrid=%s verdict=%s scores=%s turns=%s",
                emrid,
                judge_result.get("monitoring_verdict"),
                judge_result.get("quality_scores"),
                judge_result.get("turn_count"),
            )
        except Exception as exc:
            logger.warning(f"[PostBooking] judge audit failed emrid={emrid}: {exc}")
    _task_store[judge_task_id] = {"status": "done", "result": None}

    logger.info(
        "[PostBooking] pipeline_state=%s emrid=%s",
        PipelineState.COMPLETED, emrid,
    )
    # 내부 orchestration task_ids는 SSE로 소비되지 않으므로 파이프라인 완료 후 단기 TTL 적용
    for _tid in (chart_task_id, validation_task_id, judge_task_id):
        safe_create_task(cleanup_task_after_ttl(_tid, ttl=60), name=f"cleanup:{_tid}")


# 챗봇 예약 확정
@router.post("/confirm", status_code=201)
async def confirm_schedule_api(
    request: ConfirmScheduleRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 소유권 검증: 본인 반려동물의 문진(emrid)에 대해서만 예약 확정 가능
    owner_id = await get_emrid_owner_userid(db, request.emrid)
    if owner_id is None:
        raise HTTPException(status_code=404, detail="문진 정보를 찾을 수 없습니다.")
    if owner_id != current_user.userid:
        raise HTTPException(status_code=403, detail="예약 확정 권한이 없습니다.")

    schedule = await confirm_schedule(
        db=db,
        emrid=request.emrid,
        doctorid=request.doctorid,
        confirmed_time=request.confirmed_time,
        duration_min=request.duration_min
    )

    if schedule is None:
        raise HTTPException(status_code=409, detail="선택하신 시간에 이미 예약이 있습니다.")

    # 수의사 알람 생성 — 챗봇 예약 확정 시도 일반 예약과 동일하게 알람 발송
    try:
        guardian_row = await db.execute(select(Guardian).where(Guardian.emrid == request.emrid))
        guardian = guardian_row.scalar_one_or_none()
        pet_name = "반려동물"
        if guardian:
            pet_row = await db.execute(select(Pet).where(Pet.petid == guardian.petid))
            pet_obj = pet_row.scalar_one_or_none()
            if pet_obj:
                pet_name = pet_obj.petname
        confirmed_kst = schedule.confirmed_time.astimezone(KST)
        await create_alarm(
            db=db,
            doctor_id=request.doctorid,
            schedule_id=schedule.scheduleid,
            alarm_type="reservation_confirmed",
            contents=f"{pet_name} 보호자가 챗봇으로 예약을 확정했습니다. ({confirmed_kst.strftime('%m/%d %H:%M')})",
        )
    except Exception as e:
        logger.warning(f"[Alarm] chatbot confirm alarm failed schedule_id={schedule.scheduleid}: {e}")

    # Chart + Validation + Judge 파이프라인 백그라운드 실행
    chart_task_id = str(uuid.uuid4())
    validation_task_id = str(uuid.uuid4())
    judge_task_id = str(uuid.uuid4())
    for tid in (chart_task_id, validation_task_id, judge_task_id):
        _task_store[tid] = {"status": "queued", "step": ""}

    logger.info(
        "[Confirm] pipeline_state=%s emrid=%s scheduleid=%s",
        PipelineState.SCHEDULE_CONFIRMED, request.emrid, schedule.scheduleid,
    )
    safe_create_task(
        _run_post_booking_agents(
            emrid=request.emrid,
            scheduleid=schedule.scheduleid,
            duration_min=request.duration_min,
            user_id=current_user.userid,
            chart_task_id=chart_task_id,
            validation_task_id=validation_task_id,
            judge_task_id=judge_task_id,
        ),
        task_id=chart_task_id,          # 대표 task_id로 레지스트리 등록
        name="post_booking_agents",
    )
    logger.info(
        f"[Confirm] emrid={request.emrid} scheduleid={schedule.scheduleid} "
        f"chart={chart_task_id[:8]} validation={validation_task_id[:8]} judge={judge_task_id[:8]}"
    )

    # 확정 카드(챗봇)용 병원 정보 — confirm 응답에 병원명/주소/담당의 포함
    doctor_row = await db.execute(select(Doctor).where(Doctor.doctorid == schedule.doctorid))
    doctor = doctor_row.scalar_one_or_none()

    return {
        "code": 201,
        "message": "예약이 확정되었습니다.",
        "result": {
            "schedule_id": schedule.scheduleid,
            "confirmed_time": schedule.confirmed_time.astimezone(KST).isoformat() if schedule.confirmed_time else None,
            "confirmed_end_time": schedule.confirmed_end_time.astimezone(KST).isoformat() if schedule.confirmed_end_time else None,
            "status": schedule.status,
            "hospital_name": doctor.hospital_name if doctor else None,
            "hospital_address": doctor.hospital_address if doctor else None,
            "doctor_name": doctor.doctor_name if doctor else None,
            "duration_min": request.duration_min,
            "chart_task_id": chart_task_id,
            "validation_task_id": validation_task_id,
            "judge_task_id": judge_task_id,
        }
    }
