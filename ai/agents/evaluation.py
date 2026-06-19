"""Evaluation Agent — AI 산출물 사후 검증 (triage → schedule → chart).

scheduleid 하나로 DB를 직접 조회해 3개 모듈을 독립적으로 검증한다.
  Check 1 (Triage):   1A 응급도정합성 · 1B 응급도판단
                      1C 컨텍스트연속성(MCP후) · 1D 완료신호(MCP후)
                      1E 대화품질(LLM, judge.py 통합 예정)
  Check 2 (Schedule): 2A 예약타이밍 · 2B 근무시간 · 2C 빈슬롯 · 2D 핸드오프수신(MCP후)
  Check 3 (Chart):    구조체크 1~4단계(rule) → 임상품질 5단계(LLM, 추후)

Part B (에이전트 성능 평가) — MCP 구현 후 이 파일 하단에 추가:
  run_orchestrator_eval, run_reception_eval, run_triage_agent_eval,
  run_followup_filter_eval, run_mcp_health_check, run_e2e_scenarios,
  run_full_agent_report
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from pathlib import Path

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

logger = logging.getLogger("ai.agents.evaluation")


# ── 상수 ────────────────────────────────────────────────────────

LOW_URGENCY_THRESHOLD = 4
URGENCY_MAX_DAYS: dict[int, int] = {1: 0, 2: 0, 3: 2, 4: 3, 5: 3}


# ── 유틸 ────────────────────────────────────────────────────────


def _scan_red_flags(text: str) -> list[str]:
    """vet_triage.json 기준으로 보호자 발화에서 red flag 감지. 감지된 flag label 반환."""
    try:
        from ai.agents.triage.engine import _kb
        flags = _kb().get("red_flags", {}).get("flags", [])
    except Exception:
        return []

    text_nospace = text.replace(" ", "")
    found: list[str] = []
    for flag in flags:
        keywords = flag.get("keywords", [])
        if any(k in text or k in text_nospace for k in keywords):
            found.append(flag.get("label", flag.get("id", "?")))
    return found


def _module_status(checks: list[dict]) -> str:
    statuses = {c["status"] for c in checks}
    if "WARN" in statuses:
        return "WARN"
    if "ERROR" in statuses:
        return "ERROR"
    if statuses <= {"SKIPPED"}:
        return "SKIPPED"
    return "PASS"


# ── 데이터 로딩 ─────────────────────────────────────────────────

async def _load_data(scheduleid: int, db: AsyncSession) -> dict | None:
    schedule = await db.get(Schedule, scheduleid)
    if not schedule or schedule.deleted_at is not None:
        logger.warning("[Evaluation] scheduleid=%s 없음 또는 삭제됨", scheduleid)
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


# ── Check 1 — Triage ────────────────────────────────────────────

def validate_triage(
    triage: TriageResult | None,
    chat_history: ChatHistory | None,
) -> dict:
    if triage is None:
        skipped = {"status": "SKIPPED", "detail": "triage 없음"}
        return {
            "status": "SKIPPED",
            "checks": [
                {**skipped, "item": "응급도 정합성"},
                {**skipped, "item": "응급도 판단"},
                {**skipped, "item": "컨텍스트 연속성"},
                {**skipped, "item": "완료 신호"},
            ],
        }

    checks = [
        _check_1a(triage, chat_history),
        _check_1b(triage),
        # TODO(1C): MCP 구현 후 활성화
        # messages에 agent_type 태그가 추가되면 세션 분기 감지 가능
        # _check_1c(chat_history) 로 교체
        {"item": "컨텍스트 연속성", "status": "SKIPPED", "detail": "agent_type 태그 없음 (MCP 미구현)"},
        # TODO(1D): MCP 구현 후 활성화
        # 오케스트레이터로 보낸 핸드오프 신호 로그가 있어야 검증 가능
        # _check_1d(handoff_log) 로 교체
        {"item": "완료 신호", "status": "SKIPPED", "detail": "핸드오프 신호 로그 없음 (MCP 미구현)"},
    ]
    return {"status": _module_status(checks), "checks": checks}


def _check_1a(triage: TriageResult, chat_history: ChatHistory | None) -> dict:
    """1A: 보호자 발화 기준 응급 표현 vs urgency_level_num (외부 시선)."""
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


def _check_1b(triage: TriageResult) -> dict:
    """1B: 에이전트가 정리한 chief_complaint가 red flag인데 urgency_num이 낮으면 내부 모순."""
    chief = (triage.chief_complaint or "").strip()
    if not chief:
        return {"item": "응급도 판단", "status": "SKIPPED", "detail": "chief_complaint 없음"}

    signals = _scan_red_flags(chief)

    try:
        urgency_num = int(triage.urgency_level_num)
    except (TypeError, ValueError):
        return {"item": "응급도 판단", "status": "SKIPPED", "detail": "urgency_level_num 파싱 실패"}

    if signals and urgency_num >= LOW_URGENCY_THRESHOLD:
        return {
            "item": "응급도 판단",
            "status": "WARN",
            "detail": (
                f"주증상 '{chief}'이 응급 신호({signals[0]})에 해당하나 "
                f"응급도 {urgency_num}(낮음)으로 판정 — 내부 모순"
            ),
        }
    return {
        "item": "응급도 판단",
        "status": "PASS",
        "detail": f"주증상 '{chief}' — 응급도 {urgency_num} 판정 일치",
    }


# TODO(1E): 대화 품질 평가 — judge.py 통합
# 구현 시 아래 함수를 작성하고 validate_triage에서 호출할 것
#
# async def _check_1e(triage, chat_history, db) -> dict:
#     """1E: 문진 대화 품질 LLM 평가 (구 judge.py 통합).
#
#     - triage 에이전트와 다른 모델/provider 사용 (self-enhancement 편향 회피)
#     - chat_history.messages에서 agent_type="triage" 구간만 추출 (MCP 후)
#       MCP 전에는 전체 messages 사용
#     - turn_count는 코드로 직접 계산 (LLM 비의존)
#     - 4개 지표: completeness, question_efficiency, response_consistency, structuring_quality
#     - 모두 7.0 이상 → PASS, 하나라도 미만 → WARN
#     - overall(ATTENTION/OK) 집계에서 제외 — conversation_status 필드로만 노출
#     """
#     pass


# ── Check 2 — Schedule ──────────────────────────────────────────

async def validate_schedule(
    schedule: Schedule,
    triage: TriageResult | None,
    doctor: Doctor | None,
    db: AsyncSession,
) -> dict:
    checks = []

    if not schedule.confirmed_time:
        for item in ["예약 타이밍", "근무시간", "빈 슬롯"]:
            checks.append({"item": item, "status": "SKIPPED", "detail": "confirmed_time 미확정"})
    else:
        checks.append(await _check_2a(schedule, triage, doctor, db))
        checks.append(await _check_2b(schedule, doctor, db))
        checks.append(await _check_2c(schedule, db))

    # TODO(2D): MCP 구현 후 활성화
    # 문진 완료 신호 수신 기록 + emrid 일치 + Schedule 에이전트 실행 기록 확인
    # _check_2d(handoff_log, schedule) 로 교체
    checks.append({"item": "핸드오프 수신", "status": "SKIPPED", "detail": "MCP 미구현"})

    return {"status": _module_status(checks), "checks": checks}


async def _has_same_day_slots(
    schedule: Schedule,
    doctor: Doctor | None,
    db: AsyncSession,
) -> bool | None:
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

    total_min = int(
        (datetime.combine(created.date(), work.end_time)
         - datetime.combine(created.date(), work.start_time)).total_seconds() / 60
    )
    if work.lunch_start and work.lunch_end:
        total_min -= int(
            (datetime.combine(created.date(), work.lunch_end)
             - datetime.combine(created.date(), work.lunch_start)).total_seconds() / 60
        )

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


async def _check_2a(
    schedule: Schedule,
    triage: TriageResult | None,
    doctor: Doctor | None,
    db: AsyncSession,
) -> dict:
    """2A: 응급도 대비 예약 타이밍."""
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


async def _check_2b(
    schedule: Schedule,
    doctor: Doctor | None,
    db: AsyncSession,
) -> dict:
    """2B: 근무시간 준수."""
    confirmed = to_kst(schedule.confirmed_time)
    dow = confirmed.weekday()

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


async def _check_2c(schedule: Schedule, db: AsyncSession) -> dict:
    """2C: 빈 슬롯 실제 검증."""
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


# ── Check 3 — Chart ─────────────────────────────────────────────

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

    # TODO(Chart 5단계): LLM 임상 품질 평가 — Sonnet 사용
    # triage 결과와 ai_draft_json의 일관성을 LLM으로 평가
    # 전달 필드: intake_summary, soap.S, soap.A, differential_diagnosis
    # 제외 필드: thinking, soap.O, soap.P, recommended_tests, missing_info, vet_questions, cautions
    # tool_use로 JSON 강제: {"result": "PASS"|"WARN", "detail": "..."}
    # 1회 재시도 정책 (4xx 제외, 5xx/타임아웃만 재시도)
    check = {"item": "정합성", "status": "SKIPPED", "detail": "LLM 임상 품질 평가 미구현 (추후 추가)"}
    return {"status": "SKIPPED", "checks": [check]}


# ── 결과 조립 ───────────────────────────────────────────────────

def _build_result(
    triage_v: dict,
    schedule_v: dict,
    chart_v: dict,
) -> dict:
    checks = {"triage": triage_v, "schedule": schedule_v, "chart": chart_v}

    # overall은 triage/schedule/chart만 집계 — conversation(1E)은 제외
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
        "consistency_score": consistency_score,
        "summary": summary,
    }


# ── DB 저장 (upsert) ────────────────────────────────────────────

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
        row.completeness_score = None  # 완전성 체크 제거 — 항상 None
        row.consistency_score = result["consistency_score"]
        row.summary = result["summary"]
    else:
        db.add(ValidationResult(
            emrid=emrid,
            scheduleid=scheduleid,
            overall=result["overall"],
            checks=result["checks"],
            completeness_score=None,
            consistency_score=result["consistency_score"],
            summary=result["summary"],
        ))

    await db.commit()
    logger.info("[Evaluation] 저장 scheduleid=%s overall=%s", scheduleid, result["overall"])


# ── Part A 진입점 ────────────────────────────────────────────────

async def run_case_evaluation(scheduleid: int, db: AsyncSession) -> dict:
    """케이스 평가 진입점. scheduleid 하나로 triage/schedule/chart 검증."""
    logger.info("[Evaluation] 시작 scheduleid=%s", scheduleid)

    data = await _load_data(scheduleid, db)
    if data is None:
        return {"agent": "evaluation", "scheduleid": scheduleid, "error": "schedule 없음"}

    schedule: Schedule = data["schedule"]
    triage: TriageResult | None = data["triage"]
    report: Report | None = data["report"]
    chat_history: ChatHistory | None = data["chat_history"]
    doctor: Doctor | None = data["doctor"]
    emrid: int = data["emrid"]

    try:
        triage_v = validate_triage(triage, chat_history)
    except Exception as exc:
        logger.exception("[Evaluation] Check 1 오류 scheduleid=%s", scheduleid)
        triage_v = {
            "status": "ERROR",
            "checks": [{"item": "모듈 오류", "status": "ERROR", "detail": str(exc)}],
        }

    try:
        schedule_v = await validate_schedule(schedule, triage, doctor, db)
    except Exception as exc:
        logger.exception("[Evaluation] Check 2 오류 scheduleid=%s", scheduleid)
        schedule_v = {
            "status": "ERROR",
            "checks": [{"item": "모듈 오류", "status": "ERROR", "detail": str(exc)}],
        }

    try:
        chart_v = await validate_chart(triage, report)
    except Exception as exc:
        logger.exception("[Evaluation] Check 3 오류 scheduleid=%s", scheduleid)
        chart_v = {
            "status": "ERROR",
            "checks": [{"item": "모듈 오류", "status": "ERROR", "detail": str(exc)}],
        }

    result = _build_result(triage_v, schedule_v, chart_v)
    await _save_result(scheduleid, emrid, result, db)

    logger.info("[Evaluation] 완료 scheduleid=%s overall=%s", scheduleid, result["overall"])
    return {"agent": "evaluation", "scheduleid": scheduleid, **result}















# ── Part B — 에이전트 성능 평가 ─────────────────────────────────

# TODO(Part B - MCP 후): run_orchestrator_eval, run_reception_eval,
# run_triage_agent_eval, run_mcp_health_check, run_e2e_scenarios

# ── 경과 필터 테스트셋 — ai/agents/eval_cases/followup_eval_cases.json 에서 로드 ──
# 형식: {"message": str, "expected_is_followup": bool,
#         "expected_severity": "stable|worse|urgent_possible", "expected_category": str}
def _load_followup_cases() -> list[dict]:
    import json
    candidates = [
        Path(__file__).resolve().parent / "eval_cases" / "followup_eval_cases.json",
        Path("ai/agents/eval_cases/followup_eval_cases.json"),
    ]
    for p in candidates:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return []


async def run_followup_filter_eval(
    test_cases: list[dict] | None = None,
) -> dict:
    """경과 필터 AI 평가.

    Check 1: keyword_fallback 분류 Recall/Precision (빠름, 비용 없음)
    Check 2: urgent_possible 감지율 100% (안전 필수)
    Check 3: classify_followup LLM 실호출 정확도 (API 비용 발생)

    test_cases 미전달 시 ai/agents/eval_cases/followup_eval_cases.json 로드.
    """
    from ai.agents.followup_filter.schema import SeverityHint, keyword_fallback

    cases = test_cases or _load_followup_cases()
    if not cases:
        return {"agent": "followup_filter", "status": "SKIPPED", "detail": "테스트 케이스 없음"}

    checks = []

    # ── 1. 분류 Recall / Precision + 카테고리별 통계 ──────────
    tp = fp = fn = 0
    kw_predictions: list[bool] = []
    category_stats: dict[str, dict] = {}

    for case in cases:
        expected = case.get("expected_is_followup", False)
        predicted = keyword_fallback(case["message"]).is_followup
        kw_predictions.append(predicted)
        if expected and predicted:
            tp += 1
        elif not expected and predicted:
            fp += 1
        elif expected and not predicted:
            fn += 1
        # 경과 케이스만 카테고리별 집계
        if expected:
            cat = case.get("expected_category", "unknown")
            if cat not in category_stats:
                category_stats[cat] = {"kw_hit": 0, "total": 0}
            category_stats[cat]["total"] += 1
            if predicted:
                category_stats[cat]["kw_hit"] += 1

    recall = tp / (tp + fn) if (tp + fn) > 0 else None
    precision = tp / (tp + fp) if (tp + fp) > 0 else None

    if recall is None:
        checks.append({"item": "분류 Recall/Precision", "status": "SKIPPED", "detail": "경과 케이스 없음"})
    elif recall >= 0.9 and (precision is None or precision >= 0.8):
        checks.append({
            "item": "분류 Recall/Precision", "status": "PASS",
            "detail": f"Recall {recall:.0%} / Precision {precision:.0%}",
        })
    else:
        checks.append({
            "item": "분류 Recall/Precision", "status": "WARN",
            "detail": f"Recall {recall:.0%} (기준 90%) / Precision {precision:.0%} (기준 80%)",
        })

    # ── 2. 악화 신호(urgent_possible) 감지 — 100% 필수 ────────
    urgent_cases = [c for c in cases if c.get("expected_severity") == "urgent_possible"]
    urgent_detected = sum(
        1 for c in urgent_cases
        if keyword_fallback(c["message"]).severity_hint == SeverityHint.URGENT_POSSIBLE
    )
    if not urgent_cases:
        checks.append({"item": "악화 신호 감지", "status": "SKIPPED", "detail": "urgent 케이스 없음"})
    elif urgent_detected == len(urgent_cases):
        checks.append({
            "item": "악화 신호 감지", "status": "PASS",
            "detail": f"{urgent_detected}/{len(urgent_cases)} 감지",
        })
    else:
        checks.append({
            "item": "악화 신호 감지", "status": "WARN",
            "detail": f"{urgent_detected}/{len(urgent_cases)} 감지 (100% 필수)",
        })

    # ── 3. LLM 분류 정확도 (classify_followup 병렬 실호출) ──────────
    llm_tp = llm_fp = llm_fn = llm_errors = 0
    try:
        import asyncio
        from ai.agents.followup_filter.agent import classify_followup
        from ai.orchestrator.contracts import Phase, SessionContext

        async def _run_one(case: dict):
            ctx = SessionContext(
                session_id=0, userid=0, petid=0,
                pet_info={"name": "평가용"},
                hospitalid=0, emrid=None, scheduleid=None,
                user_message=case["message"], attachments=[],
                phase=Phase.BOOKED, db=None,
            )
            return await classify_followup(ctx, case["message"])

        results = await asyncio.gather(
            *[_run_one(c) for c in cases], return_exceptions=True
        )

        missed_samples: list[dict] = []
        for i, (case, res) in enumerate(zip(cases, results)):
            if isinstance(res, Exception):
                llm_errors += 1
                continue
            expected = case.get("expected_is_followup", False)
            predicted = res.is_followup
            if expected and predicted:
                llm_tp += 1
            elif not expected and predicted:
                llm_fp += 1
            elif expected and not predicted:
                llm_fn += 1
            # keyword MISS + LLM HIT → 오분류 샘플
            if expected and not kw_predictions[i] and predicted and len(missed_samples) < 5:
                missed_samples.append({
                    "message": case["message"][:60],
                    "category": case.get("expected_category", "unknown"),
                })

        llm_recall = llm_tp / (llm_tp + llm_fn) if (llm_tp + llm_fn) > 0 else None
        llm_precision = llm_tp / (llm_tp + llm_fp) if (llm_tp + llm_fp) > 0 else None

        if llm_errors == len(cases):
            checks.append({"item": "LLM 분류 정확도", "status": "SKIPPED", "detail": "모든 케이스 LLM 호출 실패"})
        elif llm_recall is None:
            checks.append({"item": "LLM 분류 정확도", "status": "SKIPPED", "detail": "경과 케이스 없음"})
        elif llm_recall >= 0.9 and (llm_precision is None or llm_precision >= 0.8):
            checks.append({
                "item": "LLM 분류 정확도", "status": "PASS",
                "detail": f"Recall {llm_recall:.0%} / Precision {llm_precision:.0%} (LLM 실호출, 오류 {llm_errors}건)",
            })
        else:
            checks.append({
                "item": "LLM 분류 정확도", "status": "WARN",
                "detail": f"Recall {llm_recall:.0%} (기준 90%) / Precision {llm_precision:.0%} (기준 80%), 오류 {llm_errors}건",
            })
    except ImportError:
        llm_recall = llm_precision = None
        missed_samples = []
        checks.append({"item": "LLM 분류 정확도", "status": "SKIPPED", "detail": "classify_followup import 실패"})

    statuses = {c["status"] for c in checks}
    overall = "WARN" if "WARN" in statuses else ("SKIPPED" if statuses <= {"SKIPPED"} else "PASS")

    return {
        "agent": "followup_filter",
        "overall": overall,
        "checks": checks,
        "metrics": {
            "keyword_recall": round(recall, 3) if recall is not None else None,
            "keyword_precision": round(precision, 3) if precision is not None else None,
            "llm_recall": round(llm_recall, 3) if llm_recall is not None else None,
            "llm_precision": round(llm_precision, 3) if llm_precision is not None else None,
            "urgent_recall": f"{urgent_detected}/{len(urgent_cases)}" if urgent_cases else "N/A",
            "total_cases": len(cases),
            "category_stats": category_stats,
            "missed_samples": missed_samples,
        },
    }

#
# async def run_orchestrator_eval(db) -> dict:
#     """오케스트레이터 라우팅 평가. MCP 구현 후 활성화.
#     - 쓰는 것: tests/router_eval.jsonl (메시지 → 예상 에이전트 정답 레이블)
#     - 확인하는 것:
#       · 라우팅 정확도 90% 이상 (triage/reception/followup_filter 올바르게 고르는지)
#       · 문진 중 유출 0건 (active_flow=triaging 중 triage/reception 외로 라우팅 안 하는지)
#       · sticky 규칙 (짧은 답변 → 문진 유지, 이탈 안 하는지)
#     """
#     pass
#
# async def run_reception_eval(db) -> dict:
#     """응대 AI 평가. MCP 구현 후 활성화.
#     - 쓰는 것: MCP 도구 호출 로그 (get_hospital_info / get_operating_hours / get_available_slots)
#     - 확인하는 것:
#       · 병원 정보·운영시간·예약 슬롯 질문에 맞는 MCP 도구를 골랐는지 (정확도 100%)
#       · 가드레일 3요소 포함 여부 (일반론 + 수의사 권고 + 예약 유도)
#       · 무관한 질문(날씨, 요리 등) 차단 100%
#     """
#     pass
#
# async def run_triage_agent_eval(db) -> dict:
#     """문진 AI 평가.
#
#     [사전 준비 필요]
#     1. tests/triage_eval.jsonl — 대화+정답 라벨 테스트셋 (팀 직접 제작)
#        형식: {"messages":[...], "expected_variables":{"SKIN":{"itching_severity":"moderate"}},
#               "expected_urgency":"GREEN", "expected_red_flag":false}
#     2. engine.py 수정 (triage 담당자):
#        · vet_triage_v3.json 경로로 업데이트
#        · red_flag_list() public 함수 추가
#
#     [쓰는 DB 컬럼 — 새 스키마 기준]
#       · extracted_variables  {섹션:{변수:값}}  슬롯 추출 F1 측정
#       · matched_discriminators [{section,label,urgency}]  응급도 점수표 정확도 측정
#       · red_flags  [label]  RED flag 감지 측정
#       · vision_evidence  {vlm_description, body_part, cnn_results}  이미지 분석 평가
#
#     [확인하는 것]
#       · 슬롯 추출 F1 90% 이상 (expected_variables vs extracted_variables)
#       · hallucination 0건 (대화에 없는 값이 extracted_variables에 들어갔는지)
#       · 응급도 점수표 정확도 95% 이상 (expected_urgency vs urgency_level)
#       · RED flag 즉시 감지 100% (expected_red_flag=true 케이스 전수)
#     """
#     pass
#
# async def run_mcp_health_check(db) -> dict:
#     """MCP 서버 연결 상태 평가. MCP 구현 후 활성화.
#     - 쓰는 것: MCP 서버 엔드포인트
#     - 확인하는 것:
#       · 연결 + list_tools + call_tool 왕복 성공 100%
#       · 도구별 성공률 99% 이상
#       · p95 응답 시간 2000ms 이내
#       · Fallback 동작 (서버 다운 시 안내 메시지 나오는지)
#     """
#     pass
#
# async def run_e2e_scenarios(db) -> dict:
#     """전체 흐름 시나리오 평가. MCP 구현 후 활성화.
#     - 쓰는 것: 시나리오 스크립트 (메시지 시퀀스 + 단계별 기대 결과)
#     - 확인하는 것:
#       · S1 정상 예약 흐름: 문진→예약→차트→평가 각 단계 결과물 DB 저장 확인
#       · S2 문진 중 끼어들기: 슬롯 보존 + 문진 복귀 (이탈 없이 돌아오는지)
#       · S6 예약 후 경과: 경과 vs 잡담 분류 + 악화 감지 시 내원 권유 포함 여부
#     """
#     pass
#
# async def run_full_agent_report(db) -> dict:
#     """전체 에이전트 성능 통합 리포트.
#     - overall_verdict: PASS / PARTIAL_FAIL / CRITICAL_FAIL
#     - CRITICAL_FAIL 조건: RED flag recall < 100% 또는 triage_leak > 0
#     - 저장: agent_eval_resultDB (validation_resultDB와 다른 테이블)
#     """
#     pass
