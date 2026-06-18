"""Validation Agent — AI 산출물 사후 검증 (triage → schedule → chart).

scheduleid 하나로 DB를 직접 조회해 3개 모듈을 독립적으로 검증한다.
  Check 1 (Triage):   1A 완전성 · 1B 유효성(LLM, 추후) · 1C 응급도외부 · 1D 응급도내부
  Check 2 (Schedule): 2A duration · 2B 예약타이밍 · 2C 근무시간 · 2D 빈슬롯
  Check 3 (Chart):    구조체크 1~4단계(rule) → 임상품질 5단계(LLM, 추후)
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_history import ChatHistory
from app.models.doctor import Doctor
from app.models.guardian import Guardian
from app.models.pet import Pet
from app.models.report import Report
from app.models.schedule import Schedule
from app.models.triage_result import TriageResult
from app.models.validation_result import ValidationResult
from app.models.vet_schedule import HospitalWeeklySchedule, VetWeeklySchedule
from app.crud.schedule import has_time_overlap
from app.utils.timezone import KST, to_kst

logger = logging.getLogger("ai.agents.validation")


# 상수 

LOW_URGENCY_THRESHOLD = 4
URGENCY_MAX_DAYS: dict[int, int] = {1: 0, 2: 0, 3: 2, 4: 3, 5: 3}

RED_FLAG_LEXICON: dict[str, list[str]] = {
    "호흡 곤란 신호": ["숨을 못", "숨을 안", "숨쉬기", "숨이 차", "호흡곤란", "헐떡", "청색", "혀가 파", "잇몸이 파"],
    "의식 저하 신호": ["의식이 없", "의식 없", "반응이 없", "반응 없", "쓰러", "기절", "축 늘어", "정신을 잃"],
    "경련 지속 신호": ["경련", "발작", "경기", "떨면서", "몸을 떨"],
    "다량 출혈 신호": ["피를 많이", "출혈이 심", "피가 멈추지", "토혈", "각혈", "혈변", "코피가 멈"],
    "중독/이물 신호": ["삼켰", "먹으면 안", "중독", "초콜릿", "양파", "포도", "쥐약", "농약"],
    "쇼크 의심 신호": ["잇몸이 하얗", "몸이 차갑", "체온이 낮", "축 처져"],
}


# 유틸 

def _is_empty(value: object) -> bool:
    """None, 빈 문자열, 미상 계열, 빈 리스트를 '없음'으로 판단."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() in ("", "?", "미상", "알 수 없음")
    if isinstance(value, list):
        return len(value) == 0
    return False


def _scan_red_flags(text: str) -> list[str]:
    """보호자 발화 텍스트에서 응급 표현 감지. 판정 아님, 감지만."""
    found: list[str] = []
    for category, phrases in RED_FLAG_LEXICON.items():
        if any(p in text for p in phrases):
            found.append(category)
    return found


def _module_status(checks: list[dict]) -> str:
    """체크 리스트에서 모듈 레벨 status 산출."""
    statuses = {c["status"] for c in checks}
    if "WARN" in statuses:
        return "WARN"
    if "ERROR" in statuses:
        return "ERROR"
    if statuses <= {"SKIPPED"}:
        return "SKIPPED"
    return "PASS"


# 데이터 로딩 

async def _load_data(scheduleid: int, db: AsyncSession) -> dict | None:
    """scheduleid로 검증에 필요한 모든 데이터를 조회한다.

    schedule이 없으면 None 반환 → run_validation 즉시 종료.
    triage / report / chat_history가 없으면 None으로 반환 → 해당 체크 SKIPPED.
    """
    schedule = await db.get(Schedule, scheduleid)
    if not schedule or schedule.deleted_at is not None:
        logger.warning("[Validation] scheduleid=%s 없음 또는 삭제됨", scheduleid)
        return None

    emrid = schedule.emrid
    doctorid = schedule.doctorid

    guardian = await db.get(Guardian, emrid)
    pet = await db.get(Pet, guardian.petid) if guardian else None

    triage_row = await db.execute(
        select(TriageResult)
        .where(TriageResult.emrid == emrid)
        .order_by(TriageResult.id.desc())
        .limit(1)
    )
    triage = triage_row.scalar_one_or_none()

    report_row = await db.execute(
        select(Report).where(Report.scheduleid == scheduleid).limit(1)
    )
    report = report_row.scalar_one_or_none()

    chat_row = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.emrid == emrid)
        .order_by(ChatHistory.id.desc())
        .limit(1)
    )
    chat_history = chat_row.scalar_one_or_none()

    doctor = await db.get(Doctor, doctorid)

    return {
        "schedule": schedule,
        "pet": pet,
        "triage": triage,
        "report": report,
        "chat_history": chat_history,
        "doctor": doctor,
        "emrid": emrid,
    }


#  Check 1 — Triage 

def validate_triage(
    pet: Pet | None,
    triage: TriageResult | None,
    chat_history: ChatHistory | None,
) -> dict:
    if triage is None:
        skipped = {"status": "SKIPPED", "detail": "triage 없음"}
        return {
            "status": "SKIPPED",
            "checks": [
                {**skipped, "item": "완전성"},
                {**skipped, "item": "유효성"},
                {**skipped, "item": "응급도 정합성"},
                {**skipped, "item": "응급도 판단"},
            ],
        }

    checks = [
        _check_1a(pet, triage),
        {"item": "유효성", "status": "SKIPPED", "detail": "LLM 미구현 (추후 추가)"},
        _check_1c(triage, chat_history),
        _check_1d(triage),
    ]
    return {"status": _module_status(checks), "checks": checks}


def _check_1a(pet: Pet | None, triage: TriageResult) -> dict:
    """1A: 필수 항목 6개 완전성."""
    fields = {
        "종":          pet.species if pet else None,
        "생년월일":    pet.birth_date if pet else None,
        "성별":        pet.gender if pet else None,
        "주증상":      triage.chief_complaint,
        "발현시점":    triage.symptom_onset,
        "증상 키워드": triage.symptom_keywords,
    }
    missing = [label for label, val in fields.items() if _is_empty(val)]
    score = round((len(fields) - len(missing)) / len(fields) * 10, 1)
    if missing:
        return {
            "item": "완전성",
            "status": "WARN",
            "detail": f"누락 항목: {', '.join(missing)}",
            "score": score,
        }
    return {"item": "완전성", "status": "PASS", "detail": "필수 항목 모두 수집됨", "score": score}


def _check_1c(triage: TriageResult, chat_history: ChatHistory | None) -> dict:
    """1C: 보호자 발화 기준 응급 표현 vs urgency_level_num."""
    if chat_history is None:
        return {"item": "응급도 정합성", "status": "SKIPPED", "detail": "chat_history 없음"}

    messages = chat_history.messages or []
    user_texts = [
        m.get("content", "")
        for m in messages
        if isinstance(m, dict) and m.get("role") == "user"
    ]
    if not user_texts:
        return {"item": "응급도 정합성", "status": "SKIPPED", "detail": "보호자 발화 없음"}

    signals = _scan_red_flags(" ".join(user_texts))

    try:
        urgency_num = int(triage.urgency_level_num)
    except (TypeError, ValueError):
        urgency_num = 5

    if signals and urgency_num >= LOW_URGENCY_THRESHOLD:
        return {
            "item": "응급도 정합성",
            "status": "WARN",
            "detail": (
                f"응급 표현 감지({', '.join(signals)}) 됐으나 "
                f"응급도 {urgency_num}(낮음)으로 책정"
            ),
        }
    if signals:
        return {
            "item": "응급도 정합성",
            "status": "PASS",
            "detail": f"응급 표현 감지({', '.join(signals)}) — 응급도 {urgency_num}와 일치",
        }
    return {"item": "응급도 정합성", "status": "PASS", "detail": "응급 표현 미감지"}


def _check_1d(triage: TriageResult) -> dict:
    """1D: triage 자신의 red_flags vs urgency_level_num 내부 일관성."""
    red_flags = triage.red_flags or []
    issues = []
    if red_flags and triage.urgency_level_num >= LOW_URGENCY_THRESHOLD:
        issues.append(f"red_flags 있으나 응급도 {triage.urgency_level_num}(낮음) — 자기 모순")
    if _is_empty(triage.vtl_basis):
        issues.append("응급도 판단 근거(vtl_basis) 누락")
    if issues:
        return {"item": "응급도 판단", "status": "WARN", "detail": " / ".join(issues)}
    return {
        "item": "응급도 판단",
        "status": "PASS",
        "detail": "red_flags와 응급도 일치, 판단 근거 있음",
    }


#  Check 2 — Schedule 

async def validate_schedule(
    schedule: Schedule,
    triage: TriageResult | None,
    doctor: Doctor | None,
    db: AsyncSession,
) -> dict:
    checks = [_check_2a(schedule)]

    if not schedule.confirmed_time:
        for item in ["예약 타이밍", "근무시간", "빈 슬롯"]:
            checks.append({"item": item, "status": "SKIPPED", "detail": "confirmed_time 미확정"})
    else:
        checks.append(await _check_2b(schedule, triage, doctor, db))
        checks.append(await _check_2c(schedule, doctor, db))
        checks.append(await _check_2d(schedule, db))

    return {"status": _module_status(checks), "checks": checks}


def _check_2a(schedule: Schedule) -> dict:
    """2A: duration_min 합리성."""
    d = schedule.duration_min
    if d is None or d <= 0:
        return {"item": "진료 시간", "status": "WARN", "detail": f"duration_min={d} (산출 실패)"}
    if d > 240:
        return {"item": "진료 시간", "status": "WARN", "detail": f"duration_min={d} (4시간 초과, 비정상)"}
    return {"item": "진료 시간", "status": "PASS", "detail": f"{d}분 산출"}


async def _has_same_day_slots(
    schedule: Schedule,
    doctor: Doctor | None,
    db: AsyncSession,
) -> bool | None:
    """created_at 당일 가용 슬롯 추정.

    Returns:
        True  → 슬롯 있었음
        False → 슬롯 없었음 (근무 없음 또는 모두 예약됨)
        None  → 판단 불가 (근무표 정보 부족)
    """
    created = to_kst(schedule.created_at)
    dow = created.weekday()

    vet_row = await db.execute(
        select(VetWeeklySchedule).where(
            VetWeeklySchedule.doctorid == schedule.doctorid,
            VetWeeklySchedule.day_of_week == dow,
        )
    )
    work = vet_row.scalar_one_or_none()

    if work is None and doctor is not None and doctor.hospitalid is not None:
        hosp_row = await db.execute(
            select(HospitalWeeklySchedule).where(
                HospitalWeeklySchedule.hospitalid == doctor.hospitalid,
                HospitalWeeklySchedule.day_of_week == dow,
            )
        )
        work = hosp_row.scalar_one_or_none()

    if work is None or not work.is_open:
        return False
    if not work.start_time or not work.end_time:
        return None

    # 총 근무 시간 (분) - 점심 제외
    total_min = int(
        (datetime.combine(created.date(), work.end_time)
         - datetime.combine(created.date(), work.start_time)).total_seconds() / 60
    )
    if work.lunch_start and work.lunch_end:
        total_min -= int(
            (datetime.combine(created.date(), work.lunch_end)
             - datetime.combine(created.date(), work.lunch_start)).total_seconds() / 60
        )

    # 당일 이미 확정된 예약 합산 (현재 schedule 제외)
    day_start = datetime.combine(created.date(), time(0, 0)).replace(tzinfo=KST)
    day_end = datetime.combine(created.date(), time(23, 59, 59)).replace(tzinfo=KST)

    booked_rows = await db.execute(
        select(Schedule).where(
            Schedule.doctorid == schedule.doctorid,
            Schedule.confirmed_time >= day_start,
            Schedule.confirmed_time <= day_end,
            Schedule.scheduleid != schedule.scheduleid,
            Schedule.deleted_at.is_(None),
        )
    )
    booked_min = sum(s.duration_min or 0 for s in booked_rows.scalars().all())

    return (total_min - booked_min) >= (schedule.duration_min or 30)


async def _check_2b(
    schedule: Schedule,
    triage: TriageResult | None,
    doctor: Doctor | None,
    db: AsyncSession,
) -> dict:
    """2B: 응급도 대비 예약 타이밍."""
    if triage is None:
        return {"item": "예약 타이밍", "status": "SKIPPED", "detail": "triage 없어 urgency 알 수 없음"}
    try:
        urgency_num = int(triage.urgency_level_num)
    except (TypeError, ValueError):
        return {"item": "예약 타이밍", "status": "SKIPPED", "detail": "urgency_level_num 파싱 실패"}

    max_days = URGENCY_MAX_DAYS.get(urgency_num, 3)
    confirmed = to_kst(schedule.confirmed_time)
    created = to_kst(schedule.created_at)
    days_gap = (confirmed.date() - created.date()).days

    if days_gap > max_days:
        had_slots = await _has_same_day_slots(schedule, doctor, db)
        if had_slots is False:
            return {
                "item": "예약 타이밍",
                "status": "PASS",
                "detail": f"응급도 {urgency_num}: 당일 슬롯 없어 {days_gap}일 후 최선 배정",
            }
        detail = f"응급도 {urgency_num} 기준 최대 {max_days}일 이내여야 하나 {days_gap}일 후 예약"
        if had_slots is True:
            detail += " (사용자 선택)"
        return {"item": "예약 타이밍", "status": "WARN", "detail": detail}

    return {
        "item": "예약 타이밍",
        "status": "PASS",
        "detail": f"응급도 {urgency_num} 기준 {days_gap}일 후 예약 (기준 {max_days}일 이내)",
    }


async def _check_2c(
    schedule: Schedule,
    doctor: Doctor | None,
    db: AsyncSession,
) -> dict:
    """2C: 근무시간 준수 (VetWeeklySchedule → HospitalWeeklySchedule fallback)."""
    confirmed = to_kst(schedule.confirmed_time)
    dow = confirmed.weekday()  # 0=월 ~ 6=일

    vet_row = await db.execute(
        select(VetWeeklySchedule).where(
            VetWeeklySchedule.doctorid == schedule.doctorid,
            VetWeeklySchedule.day_of_week == dow,
        )
    )
    work = vet_row.scalar_one_or_none()

    if work is None:
        if doctor is None or doctor.hospitalid is None:
            return {"item": "근무시간", "status": "SKIPPED", "detail": "근무표 없고 병원 정보 없음"}
        hosp_row = await db.execute(
            select(HospitalWeeklySchedule).where(
                HospitalWeeklySchedule.hospitalid == doctor.hospitalid,
                HospitalWeeklySchedule.day_of_week == dow,
            )
        )
        work = hosp_row.scalar_one_or_none()

    if work is None:
        return {"item": "근무시간", "status": "SKIPPED", "detail": "근무표 미등록"}
    if not work.is_open:
        return {"item": "근무시간", "status": "WARN", "detail": "휴무일에 예약됨"}

    appt_time = confirmed.time()
    appt_end = (confirmed + timedelta(minutes=schedule.duration_min)).time()

    issues = []
    if work.start_time and appt_time < work.start_time:
        issues.append(f"근무 시작({work.start_time}) 전 예약")
    if work.end_time and appt_end > work.end_time:
        issues.append(f"근무 종료({work.end_time}) 후 넘어감")
    if work.lunch_start and work.lunch_end:
        if appt_time < work.lunch_end and appt_end > work.lunch_start:
            issues.append(f"점심({work.lunch_start}~{work.lunch_end})과 겹침")

    if issues:
        return {"item": "근무시간", "status": "WARN", "detail": " / ".join(issues)}
    return {"item": "근무시간", "status": "PASS", "detail": "근무시간 내 예약"}


async def _check_2d(schedule: Schedule, db: AsyncSession) -> dict:
    """2D: 빈 슬롯 실제 검증 (has_time_overlap 재사용)."""
    end = schedule.confirmed_end_time or (
        schedule.confirmed_time + timedelta(minutes=schedule.duration_min)
    )
    overlap = await has_time_overlap(
        db,
        schedule.doctorid,
        schedule.confirmed_time,
        end,
        exclude_schedule_id=schedule.scheduleid,
    )
    if overlap:
        return {"item": "빈 슬롯", "status": "WARN", "detail": "예약 시간대에 다른 예약 존재 (충돌 감지)"}
    return {"item": "빈 슬롯", "status": "PASS", "detail": "충돌 없음"}


#  Check 3 — Chart 

async def validate_chart(
    triage: TriageResult | None,
    report: Report | None,
) -> dict:
    # 1단계: report 없음
    if report is None:
        return {
            "status": "SKIPPED",
            "checks": [{"item": "정합성", "status": "SKIPPED", "detail": "차트 미생성"}],
        }

    draft = report.ai_draft_json

    # 2단계: ai_draft_json 형식 오류
    if not isinstance(draft, dict):
        return {
            "status": "WARN",
            "checks": [{"item": "정합성", "status": "WARN", "detail": "ai_draft_json이 dict 아님"}],
        }

    # 3단계: intake_summary 없음
    intake = draft.get("intake_summary")
    if not isinstance(intake, dict):
        return {
            "status": "WARN",
            "checks": [{"item": "정합성", "status": "WARN", "detail": "intake_summary 없음 (차트 구조 이상)"}],
        }

    # 4단계: key_symptoms 비어있음
    if not (intake.get("key_symptoms") or []):
        return {
            "status": "WARN",
            "checks": [{"item": "정합성", "status": "WARN", "detail": "key_symptoms 비어있음 (증상 미기록)"}],
        }

    # 5단계: LLM 임상 품질 평가 (추후 구현)
    check = {"item": "정합성", "status": "SKIPPED", "detail": "LLM 임상 품질 평가 미구현 (추후 추가)"}
    return {"status": "SKIPPED", "checks": [check]}


#  결과 조립 

def _build_result(
    triage_v: dict,
    schedule_v: dict,
    chart_v: dict,
    completeness_score: float | None,
) -> dict:
    checks = {"triage": triage_v, "schedule": schedule_v, "chart": chart_v}

    all_statuses = [
        c["status"]
        for module in checks.values()
        for c in module.get("checks", [])
    ]
    overall = "ATTENTION" if "WARN" in all_statuses else "OK"

    consistency_score = None
    for c in chart_v.get("checks", []):
        if c.get("item") == "정합성":
            if c["status"] == "PASS":
                consistency_score = 10.0
            elif c["status"] == "WARN":
                consistency_score = 5.0

    warn_items = [
        c["item"]
        for module in checks.values()
        for c in module.get("checks", [])
        if c["status"] == "WARN"
    ]
    summary = (
        f"수의사 검토 권고: {', '.join(warn_items)}"
        if warn_items
        else "특이 검증 이슈 없음"
    )

    return {
        "overall": overall,
        "checks": checks,
        "completeness_score": completeness_score,
        "consistency_score": consistency_score,
        "summary": summary,
    }


#  DB 저장 (upsert) 

async def _save_result(
    scheduleid: int,
    emrid: int,
    result: dict,
    db: AsyncSession,
) -> None:
    existing = await db.execute(
        select(ValidationResult).where(ValidationResult.scheduleid == scheduleid)
    )
    row = existing.scalar_one_or_none()

    if row:
        row.overall = result["overall"]
        row.checks = result["checks"]
        row.completeness_score = result["completeness_score"]
        row.consistency_score = result["consistency_score"]
        row.summary = result["summary"]
    else:
        db.add(ValidationResult(
            emrid=emrid,
            scheduleid=scheduleid,
            overall=result["overall"],
            checks=result["checks"],
            completeness_score=result["completeness_score"],
            consistency_score=result["consistency_score"],
            summary=result["summary"],
        ))

    await db.commit()
    logger.info("[Validation] 저장 scheduleid=%s overall=%s", scheduleid, result["overall"])


#  진입점 

async def run_validation(scheduleid: int, db: AsyncSession) -> dict:
    """Validation Agent 진입점. scheduleid 하나로 triage/schedule/chart 검증."""
    logger.info("[Validation] 시작 scheduleid=%s", scheduleid)

    data = await _load_data(scheduleid, db)
    if data is None:
        return {"agent": "validation", "scheduleid": scheduleid, "error": "schedule 없음"}

    schedule: Schedule = data["schedule"]
    pet: Pet | None = data["pet"]
    triage: TriageResult | None = data["triage"]
    report: Report | None = data["report"]
    chat_history: ChatHistory | None = data["chat_history"]
    doctor: Doctor | None = data["doctor"]
    emrid: int = data["emrid"]

    try:
        triage_v = validate_triage(pet, triage, chat_history)
    except Exception as exc:
        logger.exception("[Validation] Check 1 오류 scheduleid=%s", scheduleid)
        triage_v = {
            "status": "ERROR",
            "checks": [{"item": "모듈 오류", "status": "ERROR", "detail": str(exc)}],
        }

    try:
        schedule_v = await validate_schedule(schedule, triage, doctor, db)
    except Exception as exc:
        logger.exception("[Validation] Check 2 오류 scheduleid=%s", scheduleid)
        schedule_v = {
            "status": "ERROR",
            "checks": [{"item": "모듈 오류", "status": "ERROR", "detail": str(exc)}],
        }

    try:
        chart_v = await validate_chart(triage, report)
    except Exception as exc:
        logger.exception("[Validation] Check 3 오류 scheduleid=%s", scheduleid)
        chart_v = {
            "status": "ERROR",
            "checks": [{"item": "모듈 오류", "status": "ERROR", "detail": str(exc)}],
        }

    completeness_score = next(
        (c.get("score") for c in triage_v.get("checks", []) if c["item"] == "완전성"),
        None,
    )

    result = _build_result(triage_v, schedule_v, chart_v, completeness_score)
    await _save_result(scheduleid, emrid, result, db)

    logger.info("[Validation] 완료 scheduleid=%s overall=%s", scheduleid, result["overall"])
    return {"agent": "validation", "scheduleid": scheduleid, **result}
