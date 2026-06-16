from sqlalchemy import or_, func, select, exists, not_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pet import Pet
from app.models.user import User
from app.models.emr import EMR
from app.models.schedule import Schedule
from app.models.doctor import Doctor
from app.models.prescription import Prescription
from app.models.drug import Drug
from app.models.triage_result import TriageResult
from app.models.followup import Followup
from app.models.guardian import Guardian
from app.utils.age import calculate_age


def _emr_in_hospital_exists(doctor_ids: list[int]):
    """이 병원 원장이 작성한 EMR이 해당 펫에 1건 이상 있는지 (correlate용 EXISTS)."""
    return (
        select(EMR.doctor_emrid)
        .where(EMR.petid == Pet.petid, EMR.doctorid.in_(doctor_ids))
        .correlate(Pet)
        .exists()
    )


def _schedule_in_hospital_exists(doctor_ids: list[int]):
    """이 병원 원장에게 살아있는 예약이 해당 펫에 1건 이상 있는지 (correlate용 EXISTS)."""
    return (
        select(Schedule.scheduleid)
        .join(Guardian, Schedule.emrid == Guardian.emrid)
        .where(
            Guardian.petid == Pet.petid,
            Schedule.doctorid.in_(doctor_ids),
            Schedule.deleted_at.is_(None),
        )
        .correlate(Pet)
        .exists()
    )


async def get_patient_list(
    db: AsyncSession,
    doctor_ids: list[int],
    page: int = 1,
    page_size: int = 10,
    keyword: str | None = None,
    species: str | None = None,
    active_only: bool = False,
):
    """환자 목록 조회 (병원 스코프).

    doctor_ids: 현재 병원 소속 원장 id 목록. 이 병원 원장에게 실제 예약 또는 진료가
                1건 이상 있는 펫만 반환한다(단순 병원 등록만 한 보호자는 제외).
    active_only=True: 소프트 삭제된 guardian만 남은 환자(=취소된 예약만 있는 환자)는 제외.
                      단, guardian 레코드가 아예 없는 신규 환자는 포함.
    active_only=False(기본): 병원 스코프 내 전체 환자 반환.
    """
    base = select(Pet, User).join(User, Pet.userid == User.userid)

    # 병원 스코프: 이 병원 원장에게 예약(scheduleDB) 또는 진료(EMR)가 1건 이상 있는 펫만.
    base = base.where(
        or_(
            _emr_in_hospital_exists(doctor_ids),
            _schedule_in_hospital_exists(doctor_ids),
        )
    )

    if keyword:
        like = f"%{keyword}%"
        base = base.where(
            or_(Pet.petname.ilike(like), User.name.ilike(like))
        )

    if species:
        base = base.where(Pet.species == species)

    if active_only:
        # 활성 guardian(deleted_at IS NULL)이 1건 이상 존재 → 포함
        active_guardian_exists = (
            select(Guardian.emrid)
            .where(Guardian.petid == Pet.petid)
            .where(Guardian.deleted_at.is_(None))
            .correlate(Pet)
            .exists()
        )
        # guardian 레코드 자체가 없는 신규 환자 → 포함
        no_guardian_exists = not_(
            select(Guardian.emrid)
            .where(Guardian.petid == Pet.petid)
            .correlate(Pet)
            .exists()
        )
        base = base.where(or_(active_guardian_exists, no_guardian_exists))

    # 전체 건수
    count_stmt = select(func.count()).select_from(base.subquery())
    total_count = (await db.execute(count_stmt)).scalar_one()

    # 페이지 데이터
    rows_stmt = (
        base.order_by(Pet.petid.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(rows_stmt)).all()

    return rows, total_count


async def is_pet_in_hospital(db: AsyncSession, petid: int, doctor_ids: list[int]) -> bool:
    """이 펫이 현재 병원의 환자인지 — 이 병원 원장에게 예약 또는 진료가 1건 이상 있으면 True."""
    emr_here = (
        select(EMR.doctor_emrid)
        .where(EMR.petid == petid, EMR.doctorid.in_(doctor_ids))
        .exists()
    )
    schedule_here = (
        select(Schedule.scheduleid)
        .join(Guardian, Schedule.emrid == Guardian.emrid)
        .where(
            Guardian.petid == petid,
            Schedule.doctorid.in_(doctor_ids),
            Schedule.deleted_at.is_(None),
        )
        .exists()
    )
    result = await db.execute(select(or_(emr_here, schedule_here)))
    return bool(result.scalar())


async def get_last_visit_map(
    db: AsyncSession, pet_ids: list[int], doctor_ids: list[int] | None = None
):
    """여러 반려동물의 마지막 방문일을 한 번의 쿼리로 조회한다(N+1 방지).

    소프트 삭제된 예약(scheduleDB.deleted_at)은 방문 이력에서 제외한다.
    doctor_ids 가 주어지면 해당 병원 원장 진료(EMR)만으로 방문일을 계산한다.
    """
    if not pet_ids:
        return {}

    query = (
        select(EMR.petid, func.max(Schedule.confirmed_time))
        .join(Schedule, EMR.scheduleid == Schedule.scheduleid)
        .where(EMR.petid.in_(pet_ids))
        .where(Schedule.deleted_at.is_(None))
    )
    if doctor_ids is not None:
        query = query.where(EMR.doctorid.in_(doctor_ids))
    query = query.group_by(EMR.petid)

    result = await db.execute(query)
    return {petid: last_visit for petid, last_visit in result.all()}


async def get_patient_detail(db: AsyncSession, petid: int):
    result = await db.execute(
        select(Pet, User)
        .join(User, Pet.userid == User.userid)
        .where(Pet.petid == petid)
    )
    return result.first()


async def get_patient_emr_history(
    db: AsyncSession, petid: int, doctor_ids: list[int] | None = None
):
    """환자의 진료 이력. 소프트 삭제된 예약은 제외한다.

    doctor_ids 가 주어지면 해당 병원 원장이 작성한 EMR만 반환한다(교차병원 차단).
    None 이면 스코프 없음(과거 호출 호환).
    """
    query = (
        select(EMR, Doctor, Schedule)
        .join(Doctor, EMR.doctorid == Doctor.doctorid)
        .join(Schedule, EMR.scheduleid == Schedule.scheduleid)
        .where(EMR.petid == petid)
        .where(Schedule.deleted_at.is_(None))
    )
    if doctor_ids is not None:
        query = query.where(EMR.doctorid.in_(doctor_ids))
    query = query.order_by(EMR.created_at.desc())

    result = await db.execute(query)
    return result.all()


async def get_prescriptions_by_emr(db: AsyncSession, doctor_emrid: int):
    result = await db.execute(
        select(Prescription, Drug)
        .join(Drug, Prescription.drug_id == Drug.drugid)
        .where(Prescription.doctor_emrid == doctor_emrid)
    )
    return result.all()


async def update_patient(db: AsyncSession, pet: Pet, updates: dict):
    for key, value in updates.items():
        setattr(pet, key, value)

    await db.commit()
    await db.refresh(pet)

    return pet

import json
from datetime import datetime
from app.utils.timezone import to_kst

async def build_patient_context(
    db: AsyncSession, petid: int, hospitalid: int | None = None
) -> dict:
    # 1. Fetch Pet profile
    pet_res = await db.execute(select(Pet, User).join(User, Pet.userid == User.userid).where(Pet.petid == petid))
    pet_row = pet_res.first()
    if not pet_row:
        return {"patient_context": {}}
        
    pet, user = pet_row
    
    patient_profile = {
        "pet_id": pet.petid,
        "name": pet.petname,
        "species": pet.species or "dog",
        "breed": pet.breed or "알 수 없음",
        "age": calculate_age(pet.birth_date),
        "gender": pet.gender,
        "weight_kg": float(pet.weight_kg) if pet.weight_kg else None,
        "is_neutered": bool(pet.is_neutered) if pet.is_neutered is not None else False
    }

    # 2. EMR history & Prescriptions (병원 스코프: 타 병원 EMR은 AI 컨텍스트에서 제외)
    doctor_ids = None
    if hospitalid is not None:
        from app.crud.doctor import get_doctor_ids_by_hospital
        doctor_ids = await get_doctor_ids_by_hospital(db, hospitalid)
    history_rows = await get_patient_emr_history(db, petid, doctor_ids)
    emr_history = []
    prescriptions = []
    chronic_conditions = set()

    # N+1 방지: 모든 EMR의 처방을 한 번의 쿼리로 조회 후 emrid별로 매핑한다.
    emr_ids = [emr_obj.doctor_emrid for emr_obj, _, _ in history_rows]
    prescription_map: dict[int, list] = {}
    if emr_ids:
        presc_rows = await db.execute(
            select(Prescription, Drug)
            .join(Drug, Prescription.drug_id == Drug.drugid)
            .where(Prescription.doctor_emrid.in_(emr_ids))
        )
        for prescription, drug in presc_rows.all():
            prescription_map.setdefault(prescription.doctor_emrid, []).append((prescription, drug))

    for emr_obj, doctor_obj, schedule_obj in history_rows:
        visit_dt = to_kst(schedule_obj.confirmed_time or emr_obj.created_at)

        # 수의사가 진료완료 시 작성한 실제 메모(자유 서술). 별도 진단/SOAP 필드는 없으므로
        # 이 메모를 임상 소견(diagnosis)으로 그대로 전달한다.
        vet_memo_text = emr_obj.vet_memo or ""

        emr_entry = {
            "doctor_emrid": emr_obj.doctor_emrid,
            "visit_date": visit_dt.date().isoformat() if visit_dt else "",
            "doctor_name": doctor_obj.doctor_name,
            "diagnosis": vet_memo_text,
            "vet_memo": vet_memo_text,
        }
        emr_history.append(emr_entry)

        # Chronic conditions detection — 실제 수의사 메모 기반으로 동작
        diag_lower = vet_memo_text.lower()
        if "피부염" in diag_lower or "dermatitis" in diag_lower:
            chronic_conditions.add("Atopic/Allergic Dermatitis")
        if "외이염" in diag_lower or "otitis" in diag_lower:
            chronic_conditions.add("Otitis Externa")
        if "당뇨" in diag_lower or "diabetes" in diag_lower:
            chronic_conditions.add("Diabetes Mellitus")
        if "신부전" in diag_lower or "renal" in diag_lower or "kidney" in diag_lower:
            chronic_conditions.add("Chronic Kidney Disease")

        for prescription, drug in prescription_map.get(emr_obj.doctor_emrid, []):
            prescriptions.append({
                "drug_name": drug.name,
                "dosage": prescription.dosage or "",
                "duration_days": prescription.duration_days or 0,
                "visit_date": visit_dt.date().isoformat() if visit_dt else ""
            })
            
    # 3. Triage Results
    triage_res = await db.execute(
        select(TriageResult)
        .join(Guardian, TriageResult.emrid == Guardian.emrid)
        .where(Guardian.petid == petid)
        .order_by(TriageResult.created_at.desc())
    )
    previous_triage_results = [
        {
            "urgency_level": t.urgency_level,
            "urgency_level_num": t.urgency_level_num,
            "chief_complaint": t.chief_complaint,
            "symptom_summary": t.symptom_summary,
            "created_at": t.created_at.isoformat() if t.created_at else None
        }
        for t in triage_res.scalars().all()
    ]

    # 4. Followup History
    followup_res = await db.execute(
        select(Followup)
        .join(Guardian, Followup.emrid == Guardian.emrid)
        .where(Guardian.petid == petid)
        .order_by(Followup.created_at.desc())
    )
    followup_history = [
        {
            "followup_id": f.followupid,
            "message": f.message,
            "ai_summary": f.ai_summary,
            "emergency_alert": f.emergency_alert,
            "created_at": f.created_at.isoformat() if f.created_at else None
        }
        for f in followup_res.scalars().all()
    ]

    # 5. Revisit Patterns
    avg_interval_days = None
    visit_dates = []
    for h in emr_history:
        if h.get("visit_date"):
            try:
                visit_dates.append(datetime.strptime(h["visit_date"], "%Y-%m-%d"))
            except ValueError:
                pass
    visit_dates.sort()
    if len(visit_dates) > 1:
        intervals = [(visit_dates[i] - visit_dates[i-1]).days for i in range(1, len(visit_dates))]
        avg_interval_days = float(sum(intervals) / len(intervals))
        
    revisit_patterns = {
        "total_visits": len(emr_history),
        "avg_interval_days": avg_interval_days,
        "visit_frequency": "regular" if avg_interval_days and avg_interval_days <= 60 else "irregular"
    }

    # Build canonical context dictionary
    canonical_context = {
        "patient_profile": patient_profile,
        "emr_history": emr_history,
        "prescriptions": prescriptions,
        "chronic_conditions": list(chronic_conditions),
        "revisit_patterns": revisit_patterns,
        "previous_triage_results": previous_triage_results,
        "followup_history": followup_history,
        "visit_type": "returning" if emr_history else "initial"
    }
    
    return {
        "patient_context": canonical_context
    }
