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
from app.crud.alarm import create_alarm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/schedules", tags=["schedules"])

KST = timezone(timedelta(hours=9))


async def _verify_emrid_owner(db: AsyncSession, emrid: int, current_user_id: int) -> None:
    owner_id = await get_emrid_owner_userid(db, emrid)
    if owner_id is None:
        raise HTTPException(status_code=404, detail="문진 정보를 찾을 수 없습니다.")
    if owner_id != current_user_id:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")



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

    # 수의사 확인 (doctorid 기준 첫 번째 수의사로 자동 배정)
    result = await db.execute(select(Doctor).order_by(Doctor.doctorid.asc()))
    doctor = result.scalars().first()
    if not doctor:
        raise HTTPException(status_code=404, detail="등록된 수의사가 없습니다.")

    schedule, guardian = await create_checkup_schedule(
        db=db,
        pet_id=request.pet_id,
        date=request.date,
        time=request.time,
        memo=request.memo,
        doctorid=doctor.doctorid,
        category_code=request.category_code,
    )

    if schedule is None:
        raise HTTPException(status_code=409, detail="선택하신 시간에 이미 예약이 있습니다.")

    _category_labels = {1: "정기검진", 2: "일반진료"}
    category_label = _category_labels.get(request.category_code, "정기검진")

    # 수의사 알람 생성
    try:
        await create_alarm(
            db=db,
            doctor_id=doctor.doctorid,
            schedule_id=schedule.scheduleid,
            alarm_type="reservation_confirmed",
            contents=f"{pet.petname} 보호자가 {category_label} 예약을 확정했습니다. ({request.date} {request.time})",
        )
    except Exception as e:
        logger.warning(f"[Alarm] create failed schedule_id={schedule.scheduleid}: {e}")

    return {
        "code": 201,
        "message": "예약이 완료되었습니다.",
        "result": {
            "schedule_id": schedule.scheduleid,
            "pet_name": pet.petname,
            "category": category_label,
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
    for schedule, pet, doctor, category, hospital in rows:
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
            "hospital_name": hospital.hospital_name if hospital else None,
            "hospital_address": hospital.hospital_address if hospital else None,
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
    hospitalid: int = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    slots, reason = await get_available_slots(db, date, duration_min, doctorid, hospitalid)

    return {
        "code": 200,
        "message": reason,
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


# 응급도 기반 슬롯 추천 (LangGraph: duration 산정 LLM → 3모드 슬롯 결정론)
@router.post("/recommend")
async def recommend_schedule_api(
    body: dict,
    current_user = Depends(get_current_user),
):
    """문진 완료 후 예약 단계. duration + 추천/수의사별/가장가까운 3모드를 한 번에 반환."""
    from ai.graph import run_schedule_pipeline

    result = await run_schedule_pipeline(
        pet=body.get("pet") or {},
        triage=body.get("triage") or body.get("triage_result") or {},
        hospitalid=body.get("hospitalid"),
        doctorid=body.get("doctorid"),
    )
    return {"code": 200, "message": "", "result": result}


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

    from app.models.hospital import Hospital
    hospital = None
    if doctor and doctor.hospitalid:
        hospital_row = await db.execute(select(Hospital).where(Hospital.hospitalid == doctor.hospitalid))
        hospital = hospital_row.scalar_one_or_none()

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
            "hospital_name": hospital.hospital_name if hospital else None,
            "hospital_address": hospital.hospital_address if hospital else None,
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
    await _verify_emrid_owner(db, schedule.emrid, current_user.userid)

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
    await _verify_emrid_owner(db, schedule.emrid, current_user.userid)

    if schedule.status in ["COMPLETED", "CANCELLED"]:
        raise HTTPException(status_code=400, detail="변경할 수 없는 예약입니다.")

    if schedule.confirmed_time.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="이미 지난 예약은 변경할 수 없습니다.")

    result = await update_schedule_time(db, schedule, request.confirmed_time, schedule.duration_min)

    if not result:
        raise HTTPException(status_code=409, detail="선택하신 시간에 이미 예약이 있습니다.")

    return {"code": 200, "message": "예약이 변경되었습니다."}


async def _fetch_booking_context(emrid: int) -> dict | None:
    """DB 조회 + RAG 검색. 필수 데이터(triage/pet) 없으면 None 반환."""
    from app.db.session import AsyncSessionLocal
    from app.crud.patient import build_patient_context
    from app.models.chat_history import ChatHistory

    async with AsyncSessionLocal() as db:
        triage = (await db.execute(select(TriageResult).where(TriageResult.emrid == emrid))).scalar_one_or_none()
        guardian = (await db.execute(select(Guardian).where(Guardian.emrid == emrid))).scalar_one_or_none()
        pet_row = await db.execute(select(Pet).where(Pet.petid == guardian.petid)) if guardian else None
        pet = pet_row.scalar_one_or_none() if pet_row else None

    if not triage or not pet:
        return None

    async with AsyncSessionLocal() as db:
        # 에이전트는 전체 진료 이력 조회(교차병원 포함). 수의사 화면 표시 스코핑은 별도(api/patient.py).
        patient_context_data = await build_patient_context(db, pet.petid)

    agent_chat_history: list = []
    photo_predictions: list[dict] = []
    try:
        async with AsyncSessionLocal() as db_j:
            ch = (await db_j.execute(select(ChatHistory).where(ChatHistory.emrid == emrid))).scalar_one_or_none()
            if ch and ch.messages:
                agent_chat_history = [
                    m for m in ch.messages
                    if m.get("role") in ("user", "assistant") and m.get("content")
                ]
                for m in ch.messages:
                    if not isinstance(m, dict):
                        continue
                    analysis = m.get("photo_analysis") or {}
                    image_url = m.get("image_url")
                    for key, model_type in (("skin", "skin"), ("eye", "eye")):
                        item = analysis.get(key)
                        if not isinstance(item, dict) or item.get("error"):
                            continue
                        photo_predictions.append({
                            "model_type": model_type,
                            "prediction": item.get("top_1"),
                            "top_class": item.get("top_class"),
                            "confidence": item.get("top_confidence"),
                            "details": item.get("details") or [],
                            "image_url": image_url,
                        })
    except Exception as exc:
        logger.warning(f"[PostBooking] chat_history fetch failed emrid={emrid}: {exc}")

    emr_history = patient_context_data.get("patient_context", {}).get("emr_history") or []
    is_initial_visit = len(emr_history) == 0

    chart_rag_context: list[dict] = []
    try:
        from ai.triage.rag import RAG_USABLE_THRESHOLD, search_similar_triage_cases
        from ai.observability import score_rag_retrieval
        rag_query = " ".join(filter(None, [
            triage.chief_complaint or "",
            " ".join(triage.symptom_keywords or []),
            triage.symptom_summary or "",
        ])).strip()
        if rag_query:
            async with AsyncSessionLocal() as db_rag:
                matches = await search_similar_triage_cases(db_rag, rag_query, top_k=3)
            chart_rag_context = [m.to_dict() for m in matches if m.similarity >= RAG_USABLE_THRESHOLD]
            score_rag_retrieval([m.similarity for m in matches], threshold=RAG_USABLE_THRESHOLD)
            logger.info("[PostBooking] chart RAG emrid=%s query=%r usable=%d/%d",
                        emrid, rag_query[:60], len(chart_rag_context), len(matches))
    except Exception as exc:
        logger.warning(f"[PostBooking] chart RAG skipped emrid={emrid}: {exc}")

    return {
        "triage": triage,
        "pet": pet,
        "patient_context_data": patient_context_data,
        "agent_chat_history": agent_chat_history,
        "photo_predictions": photo_predictions,
        "chart_rag_context": chart_rag_context,
        "is_initial_visit": is_initial_visit,
    }


def _build_payloads(ctx: dict, duration_min: int) -> tuple[dict, dict, dict]:
    """컨텍스트 dict → (chart_payload, validation_payload, judge_payload) 조립. 순수 함수."""
    triage = ctx["triage"]
    pet = ctx["pet"]
    patient_context_data = ctx["patient_context_data"]
    agent_chat_history = ctx["agent_chat_history"]
    photo_predictions = ctx["photo_predictions"]
    chart_rag_context = ctx["chart_rag_context"]
    is_initial_visit = ctx["is_initial_visit"]

    age = (date_type.today().year - pet.birth_date.year) if pet.birth_date else None
    pet_payload = {
        "name": pet.petname,
        "species": pet.species or "dog",
        "breed": pet.breed or "알 수 없음",
        "age": age,
        "gender": pet.gender,
        "weight": float(pet.weight_kg) if pet.weight_kg else None,
    }

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
    if photo_predictions:
        triage_info["photo_predictions"] = photo_predictions

    _URGENCY_WINDOW_MAP = {
        1: "immediate", 2: "emergency_today", 3: "urgent_24h",
        4: "semi_urgent_48h", 5: "routine_72h",
    }
    schedule_slot = {
        "estimated_duration_min": duration_min,
        "is_initial_visit": is_initial_visit,
        "slot_window": _URGENCY_WINDOW_MAP.get(triage_info.get("urgency_level_num", 3), "urgent_24h"),
    }

    chart_payload = {
        "pet": pet_payload,
        "triage_result": triage_info,
        "triage_info": triage_info,
        "patient_context": patient_context_data,
        "schedule_slot": schedule_slot,
        "schedule_result": schedule_slot,
        "rag_context": chart_rag_context,
        "chat_history": agent_chat_history,
    }
    validation_payload = {
        "pet": pet_payload,
        "triage_result": triage_info,
        "triage_info": triage_info,
        "patient_context": patient_context_data,
        "schedule_slot": schedule_slot,
        "schedule_result": schedule_slot,
    }
    judge_payload = {
        "triage_result": triage_info,
        "triage_info": triage_info,
        "chat_history": agent_chat_history,
    }

    return chart_payload, validation_payload, judge_payload


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
    logger.info(f"[PostBooking] start emrid={emrid} scheduleid={scheduleid}")

    ctx = await _fetch_booking_context(emrid)
    if ctx is None:
        logger.warning(f"[PostBooking] 필수 데이터 없음 emrid={emrid}")
        for tid in (chart_task_id, validation_task_id, judge_task_id):
            _task_store[tid] = {"status": "error", "detail": "트리아지 또는 반려동물 정보 없음"}
        return

    chart_payload, validation_payload, judge_payload = _build_payloads(ctx, duration_min)

    from ai.graph import post_booking_graph
    await post_booking_graph.ainvoke({
        "emrid": emrid,
        "scheduleid": scheduleid,
        "user_id": user_id,
        "chart_payload": chart_payload,
        "validation_payload": validation_payload,
        "judge_payload": judge_payload,
        "chart_task_id": chart_task_id,
        "validation_task_id": validation_task_id,
        "judge_task_id": judge_task_id,
    })
    _task_store[judge_task_id] = {"status": "done", "result": None}

    logger.info("[PostBooking] pipeline_state=%s emrid=%s", PipelineState.COMPLETED, emrid)
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
    await _verify_emrid_owner(db, request.emrid, current_user.userid)

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

    # Phase 3: Chart→Validation→Judge 백그라운드 파이프라인 (재작성 예정 — 현재 임시 비활성)
    chart_task_id = validation_task_id = judge_task_id = None
    logger.info(f"[Confirm] emrid={request.emrid} scheduleid={schedule.scheduleid} (post-booking 비활성)")

    # 확정 카드(챗봇)용 병원 정보 — confirm 응답에 병원명/주소/담당의 포함
    doctor_row = await db.execute(select(Doctor).where(Doctor.doctorid == schedule.doctorid))
    doctor = doctor_row.scalar_one_or_none()

    from app.models.hospital import Hospital
    hospital = None
    if doctor and doctor.hospitalid:
        hospital_row = await db.execute(select(Hospital).where(Hospital.hospitalid == doctor.hospitalid))
        hospital = hospital_row.scalar_one_or_none()

    return {
        "code": 201,
        "message": "예약이 확정되었습니다.",
        "result": {
            "schedule_id": schedule.scheduleid,
            "confirmed_time": schedule.confirmed_time.astimezone(KST).isoformat() if schedule.confirmed_time else None,
            "confirmed_end_time": schedule.confirmed_end_time.astimezone(KST).isoformat() if schedule.confirmed_end_time else None,
            "status": schedule.status,
            "hospital_name": hospital.hospital_name if hospital else None,
            "hospital_address": hospital.hospital_address if hospital else None,
            "doctor_name": doctor.doctor_name if doctor else None,
            "duration_min": request.duration_min,
            "chart_task_id": chart_task_id,
            "validation_task_id": validation_task_id,
            "judge_task_id": judge_task_id,
        }
    }
