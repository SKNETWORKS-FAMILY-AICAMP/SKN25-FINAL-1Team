import logging

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import get_current_hospital
from app.crud.tenant_guard import schedule_in_hospital
from app.utils.age import calculate_age
from app.utils.timezone import to_kst

logger = logging.getLogger(__name__)

from app.crud.doctor_reservation import (
    get_reservations,
    update_reservation_status,
    create_reservation,
    update_reservation,
    delete_reservation,
    schedule_slot_release,
    TimeSlotConflict,
)

from app.schemas.doctor_reservation import (
    ReservationCreate,
    ReservationUpdate,
    ReservationStatusUpdate,
)


router = APIRouter(
    prefix="/doctor/reservations",
    tags=["doctor-reservations"]
)


def _triage_key(triage, triage_result) -> str:
    """챗봇 문진 결과가 있으면 그 응급도를 우선 사용한다."""
    # VTL 4단계(urgency_level_num) → 화면 표시 3버킷
    def _bucket(n) -> str:
        if n == 1:
            return "emergency"      # 응급
        if n in (2, 3):
            return "semiEmergency"  # 준응급
        return "normal"             # 일반

    if triage_result:
        return _bucket(triage_result.urgency_level_num)

    if triage:
        return _bucket(triage.code)

    return "normal"


def _visit_reason(category, triage_result) -> str:
    """진료 항목은 예약 경로 기준으로 단순하게 보여준다."""
    if triage_result:
        return "일반"

    return category.label if category else ""


def _serialize_reservation(row) -> dict:
    """get_reservations 조인 결과 한 행을 응답 형태로 변환한다."""
    schedule, guardian, pet, user, doctor, triage, category, triage_result = row
    confirmed = to_kst(schedule.confirmed_time)
    end = to_kst(schedule.confirmed_end_time)

    return {
        "schedule_id": schedule.scheduleid,
        "petid": pet.petid,
        "pet_name": pet.petname,
        "species": pet.species or "",
        "breed": pet.breed or "",
        "birth_date": pet.birth_date.isoformat() if pet.birth_date else "",
        "age": calculate_age(pet.birth_date),
        "weight_kg": float(pet.weight_kg) if pet.weight_kg else 0,
        "gender": pet.gender or "",
        "is_neutered": bool(pet.is_neutered),
        "profile_image": pet.profile_image,
        "last_checkup_date": (
            pet.checkup_date.isoformat() if pet.checkup_date else ""
        ),
        "owner_name": user.name,
        "phone": user.phone,
        "doctorid": doctor.doctorid,
        "doctor_name": doctor.doctor_name,
        "visit_reason": _visit_reason(category, triage_result),
        "triage": _triage_key(triage, triage_result),
        "date": confirmed.date().isoformat() if confirmed else "",
        "start": confirmed.strftime("%H:%M") if confirmed else "",
        "end": end.strftime("%H:%M") if end else "",
        "duration_min": schedule.duration_min,
        "memo": guardian.memo or "",
        "status": schedule.status,
    }


@router.get("")
async def reservation_list(
    doctorid: Optional[int] = Query(None, description="특정 수의사 예약만 조회 (미지정 시 병원 전체)"),
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    rows = await get_reservations(db, hospital_id=current_hospital.hospitalid, doctorid=doctorid)

    return {
        "code": 200,
        "result": [_serialize_reservation(row) for row in rows],
    }


@router.post("", status_code=201)
async def add_reservation(
    request: ReservationCreate,
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    try:
        schedule = await create_reservation(
            db,
            pet_id=request.pet_id,
            date_str=request.date,
            time_str=request.time,
            doctorid=request.doctorid,
            doctor_name=request.doctor_name,
            memo=request.memo,
            category_code=request.category_code,
        )
    except TimeSlotConflict:
        raise HTTPException(
            status_code=409,
            detail="해당 시간에 이미 예약이 있습니다. 다른 시간을 선택해주세요."
        )

    if not schedule:
        raise HTTPException(
            status_code=400,
            detail="예약을 생성할 수 없습니다. (수의사/카테고리 정보를 확인하세요)"
        )

    return {
        "code": 201,
        "message": "예약이 추가되었습니다.",
        "result": {"schedule_id": schedule.scheduleid},
    }


@router.put("/{schedule_id}")
async def edit_reservation(
    schedule_id: int,
    request: ReservationUpdate,
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    # 병원 스코프: 자기 병원 예약만 수정 가능.
    if not await schedule_in_hospital(db, schedule_id, current_hospital.hospitalid):
        raise HTTPException(status_code=404, detail="예약 정보를 찾을 수 없습니다.")
    try:
        updated = await update_reservation(
            db,
            schedule_id,
            date_str=request.date,
            time_str=request.time,
            doctorid=request.doctorid,
            doctor_name=request.doctor_name,
            memo=request.memo,
        )
    except TimeSlotConflict:
        raise HTTPException(
            status_code=409,
            detail="해당 시간에 이미 예약이 있습니다. 다른 시간을 선택해주세요."
        )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="예약 정보를 찾을 수 없습니다."
        )

    return {
        "code": 200,
        "message": "예약이 수정되었습니다.",
        "result": {"schedule_id": updated.scheduleid},
    }


@router.delete("/{schedule_id}")
async def remove_reservation(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    logger.info(f"[DELETE reservation] schedule_id={schedule_id}")

    # 병원 스코프: 자기 병원 예약만 취소 가능.
    if not await schedule_in_hospital(db, schedule_id, current_hospital.hospitalid):
        raise HTTPException(status_code=404, detail="예약 정보를 찾을 수 없습니다.")

    # 존재 여부 선확인
    from app.crud.doctor_reservation import get_schedule as _get_schedule
    schedule = await _get_schedule(db, schedule_id)
    if not schedule:
        # 소프트 삭제된 경우도 포함해서 재조회
        from sqlalchemy import select as _select
        from app.models.schedule import Schedule as _Schedule
        row = await db.execute(
            _select(_Schedule).where(_Schedule.scheduleid == schedule_id)
        )
        existing = row.scalar_one_or_none()
        if existing and existing.deleted_at:
            raise HTTPException(status_code=409, detail="이미 취소된 예약입니다.")
        raise HTTPException(status_code=404, detail="예약 정보를 찾을 수 없습니다.")

    if schedule.status == "CANCELLED":
        raise HTTPException(status_code=409, detail="이미 취소된 예약입니다.")

    try:
        await delete_reservation(db, schedule_id)
        logger.info(f"[DELETE reservation] success schedule_id={schedule_id}")
    except Exception:
        logger.exception(
            f"[DELETE reservation] failed schedule_id={schedule_id}"
        )
        raise HTTPException(status_code=500, detail="예약 취소 중 오류가 발생했습니다.")

    return {
        "code": 200,
        "message": "예약이 취소되었습니다.",
        "result": {
            "success": True,
            "reservation_id": schedule_id,
        },
    }


@router.patch("/{schedule_id}")
async def change_reservation_status(
    schedule_id: int,
    request: ReservationStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_hospital=Depends(get_current_hospital),
):
    # 병원 스코프: 자기 병원 예약 상태만 변경 가능.
    if not await schedule_in_hospital(db, schedule_id, current_hospital.hospitalid):
        raise HTTPException(status_code=404, detail="예약 정보를 찾을 수 없습니다.")
    updated = await update_reservation_status(
        db,
        schedule_id,
        request.status,
        vet_memo=request.vet_memo,
        attachments=request.attachments,
        prescriptions=[p.model_dump() for p in request.prescriptions] if request.prescriptions else None,
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="예약 정보를 찾을 수 없습니다."
        )

    # 진료완료 처리 시: 유예(기본 5분) 후 남는 시간 자동 해제 예약.
    # 예상 소요시간보다 일찍 끝낸 만큼 다른 예약을 받을 수 있게 종료시각을 당긴다.
    if request.status in ("진료완료", "COMPLETED"):
        schedule_slot_release(schedule_id)

    return {
        "code": 200,
        "message": "예약 상태가 변경되었습니다."
    }
