"""수의사 EMR 관련 엔드포인트 모음.

1순위: GET  /doctor/emr/queue            - 오늘의 대기/완료 큐
        GET  /doctor/emr/queue/{id}       - EMR 상세
3순위: GET  /doctor/emr/{id}/report      - AI SOAP 초안 (reportDB)
4순위: GET  /doctor/emr/{id}/triage      - 트리아지 결과
5순위: GET  /doctor/emr/{id}/validation  - 검증 결과
6순위: GET  /doctor/emr/followup/{emrid} - 경과 모니터링 (수의사 뷰)
7순위: POST /doctor/emr/{id}/auto-prescription - AI 처방전 자동 생성
"""
import json
import re
from datetime import date

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from ai.observability import get_langfuse_handler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import or_

from app.core.config import settings
from app.core.dependencies import get_current_doctor
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.drug import Drug
from app.models.followup import Followup
from app.models.guardian import Guardian
from app.models.pet import Pet
from app.models.triage_result import TriageResult
from app.models.schedule import Schedule
from app.crud.emr_queue import (
    get_emr_queue,
    get_emr_detail,
    get_report_by_schedule,
    get_triage_by_schedule,
    get_validation_by_schedule,
)

router = APIRouter(prefix="/doctor/emr", tags=["doctor-emr"])


# ──────────────────────────────────────────────
# 1순위: EMR Queue
# ──────────────────────────────────────────────

@router.get("/queue", status_code=200)
async def emr_queue(
    target_date: date = Query(default_factory=date.today, alias="date"),
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    """오늘의 진료 대기/완료 큐를 반환한다."""
    waiting, completed = await get_emr_queue(db, current_doctor.doctorid, target_date)
    return {
        "code": 200,
        "result": {
            "waiting": waiting,
            "completed": completed,
        },
    }


@router.get("/queue/{schedule_id}", status_code=200)
async def emr_detail(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    """schedule_id 기준 EMR 상세 정보.

    환자 정보 + 트리아지 요약 (증상 키워드, 첨부 이미지, 메모)
    + 과거 진료 기록(doctorEMRDB + prescriptionDB) 반환.
    """
    detail = await get_emr_detail(db, schedule_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="해당 예약을 찾을 수 없습니다.")
    return {"code": 200, "result": detail}


# ──────────────────────────────────────────────
# 3순위: AI SOAP 초안 (reportDB)
# ──────────────────────────────────────────────

@router.get("/{schedule_id}/report", status_code=200)
async def emr_report(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    """AI Chart 에이전트가 생성한 SOAP 초안을 반환한다."""
    report = await get_report_by_schedule(db, schedule_id)
    if report is None:
        return {"code": 200, "result": None}
    return {
        "code": 200,
        "result": {
            "reportid": report.reportid,
            "emrid": report.emrid,
            "scheduleid": report.scheduleid,
            "medical_analysis": report.medical_analysis,
            "ai_draft_json": report.ai_draft_json,
            "status": report.status,
        },
    }


# ──────────────────────────────────────────────
# 4순위: 트리아지 결과
# ──────────────────────────────────────────────

@router.get("/{schedule_id}/triage", status_code=200)
async def emr_triage(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    """보호자 문진 AI 트리아지 결과를 반환한다."""
    triage = await get_triage_by_schedule(db, schedule_id)
    if triage is None:
        return {"code": 200, "result": None}
    return {
        "code": 200,
        "result": {
            "id": triage.id,
            "emrid": triage.emrid,
            "urgency_level": triage.urgency_level,
            "urgency_level_num": triage.urgency_level_num,
            "vtl_basis": triage.vtl_basis,
            "red_flags": triage.red_flags,
            "chief_complaint": triage.chief_complaint,
            "symptom_onset": triage.symptom_onset,
            "symptom_keywords": triage.symptom_keywords,
            "suspected_diseases": triage.suspected_diseases,
            "symptom_summary": triage.symptom_summary,
            "recommended_action": triage.recommended_action,
            "need_photo": triage.need_photo,
            "created_at": triage.created_at.isoformat() if triage.created_at else None,
        },
    }


# ──────────────────────────────────────────────
# 5순위: 검증 결과
# ──────────────────────────────────────────────

@router.get("/{schedule_id}/validation", status_code=200)
async def emr_validation(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    """Validation + Judge 에이전트 결과를 반환한다."""
    validation = await get_validation_by_schedule(db, schedule_id)
    if validation is None:
        return {"code": 200, "result": None}
    return {
        "code": 200,
        "result": {
            "id": validation.id,
            "emrid": validation.emrid,
            "scheduleid": validation.scheduleid,
            "overall": validation.overall,
            "checks": validation.checks,
            "completeness_score": float(validation.completeness_score) if validation.completeness_score else None,
            "accuracy_score": float(validation.accuracy_score) if validation.accuracy_score else None,
            "consistency_score": float(validation.consistency_score) if validation.consistency_score else None,
            "summary": validation.summary,
            "emr_alignment_reason": validation.emr_alignment_reason,
            "prescription_risk_reason": validation.prescription_risk_reason,
            "score_breakdown": validation.score_breakdown,
            "created_at": validation.created_at.isoformat() if validation.created_at else None,
        },
    }


# ──────────────────────────────────────────────
# 7순위: AI 처방전 자동 생성
# ──────────────────────────────────────────────

class AutoPrescriptionRequest(BaseModel):
    doctor_notes: str = ""


@router.post("/{schedule_id}/auto-prescription", status_code=200)
async def generate_auto_prescription(
    schedule_id: int,
    body: AutoPrescriptionRequest = Body(default_factory=AutoPrescriptionRequest),
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    """사전 문진 정보를 바탕으로 AI 처방 초안을 생성한다.
    triage + drugsDB 후보 약품을 바탕으로 OpenAI로 실시간 생성한다.
    """
    # triage + pet + guardian 정보 조회
    row = (await db.execute(
        select(Schedule, Guardian, Pet)
        .join(Guardian, Schedule.emrid == Guardian.emrid)
        .join(Pet, Guardian.petid == Pet.petid)
        .where(Schedule.scheduleid == schedule_id)
        .where(Schedule.deleted_at.is_(None))
    )).first()

    if not row:
        raise HTTPException(status_code=404, detail="환자 정보를 찾을 수 없습니다.")

    _, guardian, pet = row

    triage = (await db.execute(
        select(TriageResult).where(TriageResult.emrid == guardian.emrid)
    )).scalar_one_or_none()

    # 3. 나이 계산
    today = date.today()
    birth = pet.birth_date
    age = 0
    if birth:
        age = today.year - birth.year - (
            (today.month, today.day) < (birth.month, birth.day)
        )

    # 4. 증상 정보 구성
    symptoms: list[str] = []
    suspected_diseases: list[str] = []
    if triage:
        if triage.symptom_summary:
            symptoms.append(triage.symptom_summary)
        if isinstance(triage.symptom_keywords, list):
            symptoms.extend(triage.symptom_keywords)
        if isinstance(triage.suspected_diseases, list):
            suspected_diseases = triage.suspected_diseases

    # 5. drugsDB에서 후보 약품 조회
    seen_ids: set[int] = set()
    candidate_drugs: list[Drug] = []

    # 증상/질환 키워드로 관련 약품 검색
    search_terms = suspected_diseases[:3] + symptoms[:2]
    for term in search_terms:
        if len(term) < 2:
            continue
        rows = (await db.execute(
            select(Drug).where(
                or_(
                    Drug.ingredient_kr.ilike(f"%{term}%"),
                    Drug.ingredient_en.ilike(f"%{term}%"),
                    Drug.name.ilike(f"%{term}%"),
                )
            ).limit(8)
        )).scalars().all()
        for d in rows:
            if d.drugid not in seen_ids:
                seen_ids.add(d.drugid)
                candidate_drugs.append(d)

    # 부족하면 일반 약품으로 채움
    if len(candidate_drugs) < 15:
        general = (await db.execute(select(Drug).limit(40))).scalars().all()
        for d in general:
            if d.drugid not in seen_ids:
                seen_ids.add(d.drugid)
                candidate_drugs.append(d)
                if len(candidate_drugs) >= 40:
                    break

    drug_list_str = "\n".join(
        f"- {d.name} (성분: {d.ingredient_kr})"
        for d in candidate_drugs[:40]
    )

    prompt = f"""수의사 AI 보조입니다. 환자 문진 정보와 아래 약품 목록을 바탕으로 처방전을 작성하세요.

[환자 정보]
종류/품종: {pet.species or "강아지"} / {pet.breed or ""}
체중: {float(pet.weight_kg) if pet.weight_kg else 0}kg, 나이: {age}살

[사전 문진]
주요 증상: {", ".join(symptoms) if symptoms else "정보 없음"}
의심 질환: {", ".join(suspected_diseases) if suspected_diseases else "정보 없음"}
보호자 메모: {guardian.memo or "없음"}
수의사 진료 메모: {body.doctor_notes.strip() or "없음"}

[사용 가능한 약품 목록]
{drug_list_str}

위 약품 목록에서 증상에 적합한 2~4가지를 선택하고, 각 약품의 투여 형태·용량·빈도·기간을 작성하세요.
반드시 아래 허용값 중에서만 선택하세요 (목록 외 값 사용 금지):
- form(투여형태): PO(경구), IV(정맥), SC(피하), IM(근육), 외용, 점안, 흡입
- dosage(용량): 0.5mg/kg, 1mg/kg, 2mg/kg, 5mg/kg, 10mg/kg, 0.5ml, 1ml, 2ml, 5ml, 1정, 1/2정, 2정
- frequency(빈도): SID(하루 1회), BID(하루 2회), TID(하루 3회), QID(하루 4회), 필요 시
- duration(기간, 정수): 3, 5, 7, 10, 14, 30
반드시 아래 JSON 형식으로만 응답하세요 (duration은 반드시 정수):

{{
  "medications": [
    {{
      "name": "폴리펜젝트 20(POLYPENJECT 20)",
      "form": "SC(피하)",
      "dosage": "10mg/kg",
      "frequency": "SID(하루 1회)",
      "duration": 5
    }}
  ]
}}"""

    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL or "gpt-4o",
        api_key=settings.OPENAI_API_KEY,
        temperature=0.3,
        model_kwargs={"response_format": {"type": "json_object"}},
    )
    response = await llm.ainvoke(
        [
            {
                "role": "system",
                "content": "당신은 전문 수의사 AI 보조입니다. 반드시 JSON 형식으로만 응답하고, duration 필드는 반드시 숫자(정수)만 사용하세요.",
            },
            {"role": "user", "content": prompt},
        ],
        config={"run_name": "emr_medication", "callbacks": [get_langfuse_handler()]},
    )

    data = json.loads(response.content if isinstance(response.content, str) else "{}")
    meds = data.get("medications", [])

    def _to_int(val) -> int:
        m = re.search(r"\d+", str(val or ""))
        return int(m.group()) if m else 0

    return {
        "code": 200,
        "result": [
            {
                "drug_name": m.get("name", ""),
                "form": m.get("form", ""),
                "dosage": m.get("dosage", ""),
                "frequency": m.get("frequency", ""),
                "duration_days": _to_int(m.get("duration", 0)),
            }
            for m in meds
        ],
    }


# ──────────────────────────────────────────────
# 6순위: 경과 모니터링 (수의사 뷰)
# ──────────────────────────────────────────────

@router.get("/followup/{emrid}", status_code=200)
async def doctor_followup(
    emrid: int,
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    """보호자가 등록한 경과 사진/메시지를 수의사가 조회한다."""
    result = await db.execute(
        select(Followup)
        .where(Followup.emrid == emrid)
        .order_by(Followup.created_at.asc())
    )
    followups = result.scalars().all()
    return {
        "code": 200,
        "result": [
            {
                "followup_id": f.followupid,
                "emrid": f.emrid,
                "images": f.images,
                "message": f.message,
                "ai_summary": f.ai_summary,
                "emergency_alert": f.emergency_alert,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in followups
        ],
    }


# ──────────────────────────────────────────────
# 진료 사진 업로드 (의사 인증) — x-ray 등 진료 중 촬영 이미지를 S3에 올리고 읽기용 URL 반환
# ──────────────────────────────────────────────

@router.post("/upload/file", status_code=200)
async def upload_emr_file(
    file: UploadFile = File(...),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    allowed_types = ["image/jpeg", "image/png", "application/pdf", "video/mp4"]
    content_type = file.content_type or "application/octet-stream"
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="이미지(JPG, PNG), PDF 또는 영상(MP4) 파일만 업로드 가능합니다.",
        )

    body = await file.read()
    if len(body) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="파일 크기는 50MB 이하만 업로드 가능합니다.")

    from botocore.exceptions import NoCredentialsError

    from app.utils.s3 import upload_object

    try:
        result = upload_object(file.filename or "emr-attachment", content_type, body, prefix="emr")
    except NoCredentialsError:
        raise HTTPException(status_code=500, detail="S3 인증 정보가 설정되지 않았습니다.")
    return {"code": 200, "result": result}


# ──────────────────────────────────────────────
# 수의사 - 환자(펫) 정보 수정
# ──────────────────────────────────────────────

from pydantic import BaseModel as _BaseModel
from typing import Optional as _Optional

class PetUpdateByDoctor(_BaseModel):
    weight_kg: _Optional[float] = None
    notes: _Optional[str] = None
    gender: _Optional[str] = None
    birth_date: _Optional[date] = None
    checkup_date: _Optional[date] = None


@router.patch("/pet/{pet_id}", status_code=200)
async def update_pet_by_doctor(
    pet_id: int,
    body: PetUpdateByDoctor,
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    """수의사가 진료 중 체중·특이사항을 업데이트한다."""
    from app.models.pet import Pet
    result = await db.execute(select(Pet).where(Pet.petid == pet_id))
    pet = result.scalar_one_or_none()
    if not pet:
        raise HTTPException(status_code=404, detail="반려동물 정보를 찾을 수 없습니다.")

    if body.weight_kg is not None:
        pet.weight_kg = body.weight_kg
    if body.notes is not None:
        pet.notes = body.notes
    if body.gender is not None:
        pet.gender = body.gender
    if body.birth_date is not None:
        pet.birth_date = body.birth_date
    if body.checkup_date is not None:
        pet.checkup_date = body.checkup_date

    await db.commit()
    return {"code": 200, "message": "반려동물 정보가 수정되었습니다."}


# ──────────────────────────────────────────────
# 진료 완료 → 진료 대기 리셋 (EMR + 처방전 초기화)
# ──────────────────────────────────────────────

@router.post("/{schedule_id}/reset", status_code=200)
async def reset_visit(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    """진료 완료된 스케줄을 진료 대기로 되돌리고 EMR·처방전을 초기화한다."""
    from app.models.schedule import Schedule
    from app.models.emr import EMR
    from app.models.prescription import Prescription

    schedule_row = await db.execute(
        select(Schedule).where(Schedule.scheduleid == schedule_id)
    )
    schedule = schedule_row.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")

    schedule.status = "CONFIRMED"

    emr_row = await db.execute(
        select(EMR).where(EMR.scheduleid == schedule_id)
    )
    emr = emr_row.scalar_one_or_none()
    if emr:
        presc_rows = (await db.execute(
            select(Prescription).where(Prescription.doctor_emrid == emr.doctor_emrid)
        )).scalars().all()
        for p in presc_rows:
            await db.delete(p)
        await db.flush()
        await db.delete(emr)

    await db.commit()
    return {"code": 200, "message": "진료 대기로 초기화되었습니다."}
