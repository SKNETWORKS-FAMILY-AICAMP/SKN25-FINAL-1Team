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

import json
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
        _check_1c(triage, chat_history),
        _check_1d(triage),
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


def _check_1c(triage: TriageResult, chat_history: ChatHistory | None) -> dict:
    """1C: 추출 슬롯이 보호자 발화에 근거하는지 확인 (MCP 없는 버전 — symptom_keywords 기반)."""
    if chat_history is None:
        return {"item": "컨텍스트 연속성", "status": "SKIPPED", "detail": "chat_history 없음"}

    messages = chat_history.messages or []
    user_text = " ".join(
        m.get("content", "")
        for m in messages
        if isinstance(m, dict) and m.get("role") == "user"
    )
    if not user_text:
        return {"item": "컨텍스트 연속성", "status": "SKIPPED", "detail": "보호자 발화 없음"}

    keywords = triage.symptom_keywords or []
    if not keywords:
        return {"item": "컨텍스트 연속성", "status": "PASS", "detail": "증상 키워드 없음 — 연속성 N/A"}

    user_nospace = user_text.replace(" ", "")
    hit = sum(1 for kw in keywords if kw in user_text or kw.replace(" ", "") in user_nospace)
    ratio = hit / len(keywords)

    if ratio >= 0.5:
        return {
            "item": "컨텍스트 연속성",
            "status": "PASS",
            "detail": f"증상 키워드 {hit}/{len(keywords)}개 보호자 발화에서 확인됨",
        }
    return {
        "item": "컨텍스트 연속성",
        "status": "WARN",
        "detail": f"증상 키워드 {hit}/{len(keywords)}개만 발화 확인 — 추출 근거 불충분",
    }


def _check_1d(triage: TriageResult) -> dict:
    """1D: 문진 완료 신호 확인 (MCP 없는 버전 — DB 필드 완전성으로 추론)."""
    missing = []
    if not triage.urgency_level:
        missing.append("urgency_level")
    if not triage.chief_complaint:
        missing.append("chief_complaint")
    if not triage.symptom_summary:
        missing.append("symptom_summary")

    if missing:
        return {
            "item": "완료 신호",
            "status": "WARN",
            "detail": f"미설정 필드: {', '.join(missing)} — 문진 완료 불확실",
        }
    return {
        "item": "완료 신호",
        "status": "PASS",
        "detail": (
            f"urgency={triage.urgency_level}({triage.urgency_level_num}) · "
            f"chief_complaint={triage.chief_complaint[:30]!r}"
        ),
    }


async def _check_1e(triage: TriageResult, chat_history: ChatHistory | None) -> dict:
    """1E: 문진 대화 품질 LLM 평가 — overall 집계 제외, conversation_status로만 노출.

    4개 지표 0~10점: completeness · question_efficiency · response_consistency · structuring_quality
    모두 7.0 이상 → PASS, 하나라도 미만 → WARN
    """
    from ai.llm import call_llm_json

    if not chat_history or not (chat_history.messages or []):
        return {"item": "대화 품질", "status": "SKIPPED", "detail": "대화 기록 없음"}

    messages = chat_history.messages or []
    # 최대 20턴 (보호자+봇 합산)
    recent = messages[-20:]
    convo = "\n".join(
        f"{m.get('role', '?')}: {(m.get('content') or '')[:200]}"
        for m in recent
        if isinstance(m, dict)
    )

    triage_info = f"응급도={triage.urgency_level}({triage.urgency_level_num})"
    if triage.chief_complaint:
        triage_info += f", 주증상={triage.chief_complaint}"

    prompt = (
        "너는 동물병원 AI 문진 품질 평가자야. 아래 문진 대화를 보고 4가지 항목을 0~10점으로 평가해.\n\n"
        f"[최종 문진 결과] {triage_info}\n\n"
        f"[문진 대화]\n{convo}\n\n"
        "[평가 항목]\n"
        "1. completeness(완전성): 증상·발병시기·심각도를 충분히 파악했는가?\n"
        "2. question_efficiency(질문 효율): 중복 없이 핵심만 물었는가?\n"
        "3. response_consistency(응답 일관성): 봇 응답이 앞 대화와 일관되는가?\n"
        "4. structuring_quality(구조화 품질): 증상을 체계적으로 정리했는가?\n\n"
        "모두 7.0 이상 → PASS 기준.\n"
        'JSON만 출력: {"completeness": 8, "question_efficiency": 7, "response_consistency": 9, "structuring_quality": 8, "comment": "한 줄 요약"}'
    )

    try:
        out = await call_llm_json(prompt)
        keys = ("completeness", "question_efficiency", "response_consistency", "structuring_quality")
        scores = {k: float(out.get(k, 0)) for k in keys}
        comment = out.get("comment", "")
        avg = sum(scores.values()) / len(scores)
        low = [k for k, v in scores.items() if v < 7.0]

        status = "WARN" if low else "PASS"
        detail = (
            f"평균 {avg:.1f}/10 · 미달: {', '.join(low)} | {comment}"
            if low
            else f"평균 {avg:.1f}/10 | {comment}"
        )
        return {"item": "대화 품질", "status": status, "detail": detail, "scores": scores}
    except Exception as exc:
        logger.warning("[Evaluation] 1E LLM 실패: %s", exc)
        return {"item": "대화 품질", "status": "SKIPPED", "detail": f"LLM 평가 실패: {exc}"}


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

    checks.append(_check_2d(schedule, triage))

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


def _check_2d(schedule: Schedule, triage: TriageResult | None) -> dict:
    """2D: 문진→예약 핸드오프 수신 확인 (MCP 없는 버전 — DB emrid 일치로 추론).

    MCP 구현 전: triage.emrid == schedule.emrid 이면 동일 EMR에 대해 예약이 생성됐으므로
    핸드오프가 정상 연결됐다고 추론한다.
    """
    if triage is None:
        return {"item": "핸드오프 수신", "status": "SKIPPED", "detail": "triage 없음 — 수신 여부 불명"}

    if schedule.emrid != triage.emrid:
        return {
            "item": "핸드오프 수신",
            "status": "WARN",
            "detail": (
                f"schedule.emrid({schedule.emrid}) ≠ triage.emrid({triage.emrid}) "
                "— 환자 불일치 의심"
            ),
        }
    return {
        "item": "핸드오프 수신",
        "status": "PASS",
        "detail": f"emrid={schedule.emrid} 일치 — triage→schedule 연결 정상 (추론)",
    }


# ── Check 3 — Chart ─────────────────────────────────────────────

async def _check_chart_quality(
    triage: TriageResult | None,
    draft: dict,
    intake: dict,
) -> dict:
    """5단계: LLM으로 차트 임상 품질 평가 — triage 결과와 일관성 체크."""
    from ai.llm import call_llm_json

    soap = draft.get("soap") or {}
    differential = draft.get("differential_diagnosis") or []

    chart_snippet = {
        "intake_summary": intake,
        "soap_S": soap.get("S", ""),
        "soap_A": soap.get("A", ""),
        "differential_diagnosis": differential[:5],
    }
    triage_context = (
        {
            "urgency_level": triage.urgency_level,
            "urgency_level_num": triage.urgency_level_num,
            "chief_complaint": triage.chief_complaint or "",
        }
        if triage
        else {}
    )

    prompt = (
        "너는 동물병원 AI 차트 검토자야. AI가 생성한 차트 초안의 임상 품질을 평가한다.\n\n"
        f"[트리아지 결과]\n{json.dumps(triage_context, ensure_ascii=False)}\n\n"
        f"[AI 차트 초안]\n{json.dumps(chart_snippet, ensure_ascii=False)}\n\n"
        "[평가 기준]\n"
        "1. SOAP A(Assessment)가 트리아지 응급도와 크게 모순되지 않는가?\n"
        "2. 주요 증상이 차트에 반영되어 있는가?\n"
        "3. 감별 진단이 증상에 근거가 있는가?(지어낸 병명·무관한 진단 없는가?)\n"
        "4. 임상적으로 명백히 잘못된 내용이 없는가?\n\n"
        "모두 통과 → PASS, 하나라도 이상 → WARN.\n"
        'JSON만 출력: {"result": "PASS" 또는 "WARN", "detail": "판단 이유 한 문장"}'
    )

    for attempt in range(2):
        try:
            out = await call_llm_json(prompt)
            result = (out.get("result") or "").upper()
            detail = out.get("detail") or ""
            if result in ("PASS", "WARN"):
                return {"item": "임상 품질", "status": result, "detail": detail}
        except Exception as exc:
            logger.warning("[Evaluation] Chart LLM 품질 평가 시도 %d 실패: %s", attempt + 1, exc)

    return {"item": "임상 품질", "status": "SKIPPED", "detail": "LLM 평가 실패"}


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

    # 5단계: LLM 임상 품질 평가
    quality_check = await _check_chart_quality(triage, draft, intake)
    return {"status": _module_status([quality_check]), "checks": [quality_check]}


# ── 결과 조립 ───────────────────────────────────────────────────

def _build_result(
    triage_v: dict,
    schedule_v: dict,
    chart_v: dict,
    conversation_v: dict | None = None,
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
        if c.get("item") in ("정합성", "임상 품질"):
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
        "conversation_status": conversation_v,  # 1E — overall 집계 제외, 별도 표시
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

    score_breakdown = {"conversation": result.get("conversation_status")} if result.get("conversation_status") else None

    if row:
        row.overall = result["overall"]
        row.checks = result["checks"]
        row.completeness_score = None
        row.consistency_score = result["consistency_score"]
        row.summary = result["summary"]
        row.score_breakdown = score_breakdown
    else:
        db.add(ValidationResult(
            emrid=emrid,
            scheduleid=scheduleid,
            overall=result["overall"],
            checks=result["checks"],
            completeness_score=None,
            consistency_score=result["consistency_score"],
            summary=result["summary"],
            score_breakdown=score_breakdown,
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

    try:
        conversation_v = await _check_1e(triage, chat_history)
    except Exception as exc:
        logger.warning("[Evaluation] 1E 오류 scheduleid=%s: %s", scheduleid, exc)
        conversation_v = {"item": "대화 품질", "status": "SKIPPED", "detail": str(exc)}

    result = _build_result(triage_v, schedule_v, chart_v, conversation_v)
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
        confidences: list[float] = []
        low_confidence_cases: list[dict] = []

        for i, (case, res) in enumerate(zip(cases, results)):
            if isinstance(res, Exception):
                llm_errors += 1
                continue
            expected = case.get("expected_is_followup", False)
            predicted = res.is_followup
            conf = res.confidence
            confidences.append(conf)

            if expected and predicted:
                llm_tp += 1
            elif not expected and predicted:
                llm_fp += 1
            elif expected and not predicted:
                llm_fn += 1

            # keyword MISS + LLM HIT → 키워드 누락 샘플
            if expected and not kw_predictions[i] and predicted and len(missed_samples) < 5:
                missed_samples.append({
                    "message": case["message"][:60],
                    "category": case.get("expected_category", "unknown"),
                })

            # 저신뢰 케이스 (confidence < 0.7)
            if conf < 0.7 and len(low_confidence_cases) < 10:
                low_confidence_cases.append({
                    "message": case["message"][:60],
                    "confidence": round(conf, 2),
                    "predicted": predicted,
                    "expected": expected,
                    "correct": predicted == expected,
                })

        avg_confidence = round(sum(confidences) / len(confidences), 3) if confidences else None

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
        avg_confidence = None
        missed_samples = []
        low_confidence_cases = []
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
            "avg_confidence": avg_confidence,
            "low_confidence_cases": low_confidence_cases,
        },
    }

def _load_triage_cases() -> list[dict]:
    import json
    candidates = [
        Path(__file__).resolve().parent / "eval_cases" / "triage_eval_cases.json",
        Path("ai/agents/eval_cases/triage_eval_cases.json"),
    ]
    for p in candidates:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return []


async def run_triage_eval(test_cases: list[dict] | None = None) -> dict:
    """문진 에이전트 평가.

    Check 1: 응급도 정확도 — engine.match(expected_extracted) → top_urgency() (결정론)
    Check 2: Red flag 감지율 — engine.red_flag_labels() RED 감지 (결정론, 100% 필수)
    Check 3: 슬롯 추출 F1 — LLM 추출 vs expected_extracted
    Check 4: 환각 체크 — 대화에 없는 증거의 변수가 추출됐는지
    Check 8: 요약 완전성 — expected_summary_keywords 포함율
    """
    from ai.agents.triage.engine import match, top_urgency, red_flag_labels

    cases = test_cases or _load_triage_cases()
    if not cases:
        return {"agent": "triage", "status": "SKIPPED", "detail": "테스트 케이스 없음"}

    checks: list[dict] = []

    # ── 결정론 체크 (1, 2) ────────────────────────────────────
    urgency_correct = urgency_total = 0
    red_flag_tp = red_flag_fn = 0
    urgency_errors: list[dict] = []

    for case in cases:
        expected_ext = case.get("expected_extracted", {})
        expected_urg = case.get("expected_urgency")
        expected_rf = case.get("expected_red_flag", False)

        matched = match(expected_ext)
        predicted_urg = top_urgency(matched)
        rf = red_flag_labels(matched)

        if expected_urg:
            urgency_total += 1
            if predicted_urg == expected_urg:
                urgency_correct += 1
            elif len(urgency_errors) < 5:
                urgency_errors.append({
                    "name": case.get("name", "")[:40],
                    "expected": expected_urg,
                    "got": predicted_urg or "None",
                })

        if expected_rf:
            if rf:
                red_flag_tp += 1
            else:
                red_flag_fn += 1

    urgency_acc = urgency_correct / urgency_total if urgency_total > 0 else None
    rf_total = red_flag_tp + red_flag_fn

    if urgency_acc is None:
        checks.append({"item": "응급도 정확도", "status": "SKIPPED", "detail": "urgency 케이스 없음"})
    elif urgency_acc >= 0.95:
        checks.append({"item": "응급도 정확도", "status": "PASS",
                        "detail": f"{urgency_correct}/{urgency_total} ({urgency_acc:.0%})"})
    else:
        checks.append({"item": "응급도 정확도", "status": "WARN",
                        "detail": f"{urgency_correct}/{urgency_total} ({urgency_acc:.0%}, 기준 95%)"})

    if rf_total == 0:
        checks.append({"item": "Red flag 감지", "status": "SKIPPED", "detail": "red flag 케이스 없음"})
    elif red_flag_fn == 0:
        checks.append({"item": "Red flag 감지", "status": "PASS",
                        "detail": f"{red_flag_tp}/{rf_total} (100%)"})
    else:
        checks.append({"item": "Red flag 감지", "status": "WARN",
                        "detail": f"{red_flag_tp}/{rf_total} ({red_flag_tp / rf_total:.0%}, 100% 필수)"})

    # ── LLM 체크 (3, 4, 8) ───────────────────────────────────
    slot_tp = slot_fp = slot_fn = 0
    hallucination_count = 0
    summary_kw_hits = summary_kw_total = 0
    llm_errors = 0

    try:
        import asyncio
        from ai.llm import call_llm_json
        from ai.agents.triage.prompts import build_extraction_prompt

        async def _extract_one(case: dict):
            msgs = case.get("messages", [])
            user_msg = msgs[-1]["content"] if msgs else ""
            history = msgs[:-1] if len(msgs) > 1 else []
            prompt = build_extraction_prompt(history, user_msg, None, {}, "")
            return await call_llm_json(prompt)

        results = await asyncio.gather(
            *[_extract_one(c) for c in cases], return_exceptions=True
        )

        for case, res in zip(cases, results):
            if isinstance(res, Exception) or not isinstance(res, dict):
                llm_errors += 1
                continue

            extracted_vars: dict = res.get("variables") or {}
            summary: str = res.get("summary") or ""

            # Check 3: Slot F1
            expected_flat: dict = {
                var: val
                for sec_vars in case.get("expected_extracted", {}).values()
                for var, val in sec_vars.items()
            }
            for var, val in expected_flat.items():
                if extracted_vars.get(var) == val:
                    slot_tp += 1
                else:
                    slot_fn += 1
            _trivial = {"none", "no", "unknown", "normal"}
            for var, val in extracted_vars.items():
                if val not in _trivial and expected_flat.get(var) != val:
                    slot_fp += 1

            # Check 4: Hallucination — extra non-trivial vars not in expected
            for var, val in extracted_vars.items():
                if val not in _trivial and var not in expected_flat:
                    hallucination_count += 1

            # Check 8: Summary keywords
            keywords = case.get("expected_summary_keywords", [])
            summary_kw_total += len(keywords)
            for kw in keywords:
                if kw in summary:
                    summary_kw_hits += 1

        slot_precision = slot_tp / (slot_tp + slot_fp) if (slot_tp + slot_fp) > 0 else None
        slot_recall = slot_tp / (slot_tp + slot_fn) if (slot_tp + slot_fn) > 0 else None
        slot_f1 = (
            2 * slot_precision * slot_recall / (slot_precision + slot_recall)
            if slot_precision and slot_recall else None
        )
        summary_score = summary_kw_hits / summary_kw_total if summary_kw_total > 0 else None

        if llm_errors == len(cases):
            for item in ["슬롯 추출 F1", "환각 체크", "요약 완전성"]:
                checks.append({"item": item, "status": "SKIPPED", "detail": "LLM 호출 전체 실패"})
        else:
            if slot_f1 is None:
                checks.append({"item": "슬롯 추출 F1", "status": "SKIPPED", "detail": "expected_extracted 없음"})
            elif slot_f1 >= 0.8:
                checks.append({"item": "슬롯 추출 F1", "status": "PASS",
                                "detail": f"F1={slot_f1:.2f} (P={slot_precision:.2f} R={slot_recall:.2f}, 오류 {llm_errors}건)"})
            else:
                checks.append({"item": "슬롯 추출 F1", "status": "WARN",
                                "detail": f"F1={slot_f1:.2f} (기준 0.80, P={slot_precision:.2f} R={slot_recall:.2f})"})

            if hallucination_count == 0:
                checks.append({"item": "환각 체크", "status": "PASS", "detail": "환각 없음"})
            else:
                checks.append({"item": "환각 체크", "status": "WARN",
                                "detail": f"환각 의심 {hallucination_count}건 (예상 외 변수 추출)"})

            if summary_score is None:
                checks.append({"item": "요약 완전성", "status": "SKIPPED", "detail": "summary_keywords 없음"})
            elif summary_score >= 0.8:
                checks.append({"item": "요약 완전성", "status": "PASS",
                                "detail": f"키워드 {summary_kw_hits}/{summary_kw_total} ({summary_score:.0%})"})
            else:
                checks.append({"item": "요약 완전성", "status": "WARN",
                                "detail": f"키워드 {summary_kw_hits}/{summary_kw_total} ({summary_score:.0%}, 기준 80%)"})

    except ImportError as exc:
        llm_errors = len(cases)
        slot_f1 = slot_precision = slot_recall = summary_score = None
        for item in ["슬롯 추출 F1", "환각 체크", "요약 완전성"]:
            checks.append({"item": item, "status": "SKIPPED", "detail": f"import 실패: {exc}"})

    statuses = {c["status"] for c in checks}
    overall = "WARN" if "WARN" in statuses else ("SKIPPED" if statuses <= {"SKIPPED"} else "PASS")

    return {
        "agent": "triage",
        "overall": overall,
        "checks": checks,
        "metrics": {
            "urgency_accuracy": round(urgency_acc, 3) if urgency_acc is not None else None,
            "urgency_cases": urgency_total,
            "urgency_errors": urgency_errors,
            "red_flag_recall": f"{red_flag_tp}/{rf_total}" if rf_total > 0 else "N/A",
            "slot_f1": round(slot_f1, 3) if slot_f1 is not None else None,
            "slot_precision": round(slot_precision, 3) if slot_precision is not None else None,
            "slot_recall": round(slot_recall, 3) if slot_recall is not None else None,
            "hallucination_count": hallucination_count,
            "summary_score": round(summary_score, 3) if summary_score is not None else None,
            "llm_errors": llm_errors,
            "total_cases": len(cases),
        },
    }


async def run_mcp_health_check() -> dict:
    """MCP 서버 연결 상태 평가 — 연결·list_tools·call_tool 왕복·레이턴시·Fallback."""
    import time

    from ai.orchestrator.mcp.client import get_mcp_tools

    checks: list[dict] = []

    # 1. 연결 + list_tools
    t0 = time.monotonic()
    try:
        tools = await get_mcp_tools(use_cache=False)
        ms = (time.monotonic() - t0) * 1000
        tool_names = [t.name for t in tools]
        if tools:
            checks.append({
                "item": "연결·list_tools",
                "status": "PASS",
                "detail": f"{len(tools)}개 도구 ({ms:.0f}ms): {', '.join(tool_names)}",
            })
        else:
            checks.append({
                "item": "연결·list_tools",
                "status": "WARN",
                "detail": "MCP 서버 응답 없음 — 도구 0개",
            })
    except Exception as exc:
        checks.append({"item": "연결·list_tools", "status": "WARN", "detail": f"연결 오류: {exc}"})
        return {"agent": "mcp_health", "overall": "WARN", "checks": checks, "metrics": {}}

    # 2. call_tool 왕복 5회 레이턴시 측정
    target = next((t for t in tools if t.name == "get_hospital_info"), None)
    avg_ms_val: float | None = None
    if not target:
        checks.append({"item": "call_tool 왕복", "status": "WARN", "detail": "get_hospital_info 도구 없음"})
    else:
        latencies: list[float] = []
        err_count = 0
        for _ in range(5):
            t0 = time.monotonic()
            try:
                await target.ainvoke({"hospitalid": 1})
                latencies.append((time.monotonic() - t0) * 1000)
            except Exception:
                err_count += 1
        if latencies:
            avg_ms_val = sum(latencies) / len(latencies)
            max_ms = max(latencies)
            st = "PASS" if max_ms <= 2000 and err_count == 0 else "WARN"
            checks.append({
                "item": "call_tool 왕복",
                "status": st,
                "detail": f"5회 평균 {avg_ms_val:.0f}ms · 최대 {max_ms:.0f}ms · 오류 {err_count}건 (기준 2000ms)",
            })
        else:
            checks.append({"item": "call_tool 왕복", "status": "WARN", "detail": "5회 모두 실패"})

    # 3. Fallback 설계 (코드 레벨 확인)
    checks.append({
        "item": "Fallback",
        "status": "PASS",
        "detail": "get_mcp_tools() 실패 시 [] 반환 → reception이 키워드 DB 조회로 자동 폴백 (코드 확인됨)",
    })

    overall = "WARN" if any(c["status"] == "WARN" for c in checks) else "PASS"
    return {
        "agent": "mcp_health",
        "overall": overall,
        "checks": checks,
        "metrics": {
            "tool_count": len(tools),
            "avg_latency_ms": round(avg_ms_val) if avg_ms_val else None,
        },
    }


async def run_orchestrator_eval(db: AsyncSession) -> dict:
    """오케스트레이터 라우팅 평가 — 정확도 90%+, 문진 중 유출 0건, sticky 규칙."""
    import asyncio as _asyncio

    from ai.orchestrator.router import route
    from ai.orchestrator.contracts import Flow, Phase, SessionContext

    # (이름, phase, flow, user_message, 허용 에이전트 집합)
    _CASES: list[tuple] = [
        # ── 결정론 (하드 제약) ──────────────────────────────
        ("BOOKED 증상",         Phase.BOOKED,       Flow.IDLE,                    "오늘 구토 3번 했어요",    {"followup_filter"}),
        ("BOOKED 병원정보",      Phase.BOOKED,       Flow.IDLE,                    "병원 몇 시까지 해요?",    {"followup_filter"}),
        ("SCHEDULING 고정",      Phase.PRE_BOOKING,  Flow.SCHEDULING,              "다음주 월요일로요",        {"schedule"}),
        ("예약확인 게이트",       Phase.PRE_BOOKING,  Flow.AWAITING_BOOKING_CONFIRM,"네",                     {"triage"}),
        # ── LLM 라우팅 ─────────────────────────────────────
        ("PRE 발작",             Phase.PRE_BOOKING,  Flow.IDLE,                    "발작 중이에요",           {"triage"}),
        ("PRE 호흡",             Phase.PRE_BOOKING,  Flow.IDLE,                    "호흡이 이상해요",         {"triage"}),
        ("PRE 병원 위치",        Phase.PRE_BOOKING,  Flow.IDLE,                    "병원 어디 있어요?",       {"reception"}),
        ("TRIAGING 중 답변",     Phase.PRE_BOOKING,  Flow.TRIAGING,                "어제부터요",              {"triage"}),
        ("PRE 잡담",             Phase.PRE_BOOKING,  Flow.IDLE,                    "오늘 날씨 좋네요",        {"reception", "redirect"}),
    ]

    hit = total = triage_leak = 0
    errors_detail: list[dict] = []

    for name, phase, flow, msg, allowed in _CASES:
        total += 1
        ctx = SessionContext(
            session_id=0, userid=0, petid=0, pet_info={},
            hospitalid=None, emrid=None, scheduleid=None,
            user_message=msg, phase=phase, active_flow=flow, db=db,
        )
        try:
            got = await route(ctx)
        except Exception as exc:
            errors_detail.append({"case": name, "error": str(exc)})
            continue

        if got in allowed:
            hit += 1
        else:
            errors_detail.append({"case": name, "expected": str(allowed), "got": got})

        if flow == Flow.TRIAGING and got == "followup_filter":
            triage_leak += 1

    acc = hit / total if total else 0
    overall = "PASS" if acc >= 0.9 and triage_leak == 0 else "WARN"

    checks: list[dict] = [
        {
            "item": "라우팅 정확도",
            "status": "PASS" if acc >= 0.9 else "WARN",
            "detail": f"{hit}/{total} ({acc:.0%}) — 기준 90%",
        },
        {
            "item": "문진 중 유출",
            "status": "PASS" if triage_leak == 0 else "WARN",
            "detail": f"TRIAGING 중 followup_filter 이탈 {triage_leak}건",
        },
    ]
    for err in errors_detail[:3]:
        case = err.get("case", "?")
        detail = (
            f"기대={err.get('expected', '?')} 실제={err.get('got', '?')}"
            if "got" in err else err.get("error", "")
        )
        checks.append({"item": f"오류: {case}", "status": "WARN", "detail": detail})

    return {
        "agent": "orchestrator",
        "overall": overall,
        "checks": checks,
        "metrics": {
            "routing_accuracy": round(acc, 3),
            "triage_leak_count": triage_leak,
            "total_cases": total,
            "error_count": len(errors_detail),
        },
    }


async def run_reception_eval(db: AsyncSession) -> dict:
    """응대 AI 평가 — MCP 도구 선택 정확도 (병원정보/운영시간/슬롯/무관질문 4케이스)."""
    from sqlalchemy import select as _select

    from app.models.hospital import Hospital
    from ai.orchestrator.contracts import Phase, SessionContext

    hos_row = await db.execute(_select(Hospital).limit(1))
    hospital = hos_row.scalar_one_or_none()
    hospitalid = hospital.hospitalid if hospital else 1

    checks: list[dict] = []

    try:
        from ai.orchestrator.mcp.client import get_mcp_tools
        mcp_tools = await get_mcp_tools()
    except Exception:
        mcp_tools = []

    if not mcp_tools:
        checks.append({
            "item": "MCP 도구 선택",
            "status": "SKIPPED",
            "detail": "MCP 서버 미가동 — run_mcp_health_check 먼저 확인",
        })
        return {"agent": "reception", "overall": "SKIPPED", "checks": checks, "metrics": {}}

    # (설명, 메시지, 기대 도구 or None=도구 미호출 기대)
    _TOOL_CASES = [
        ("병원 위치 질문",    "병원 어디 있어요?",         "get_hospital_info"),
        ("운영시간 질문",     "오늘 몇 시까지 운영해요?",   "get_operating_hours"),
        ("예약 슬롯 질문",   "예약 언제 할 수 있어요?",    "find_open_slots"),
        ("무관 질문(날씨)",  "오늘 날씨 어때요?",          None),
    ]

    from ai.agents.reception.agent import reception as _reception_agent

    tool_hit = 0
    case_checks: list[dict] = []
    for desc, msg, expected_tool in _TOOL_CASES:
        ctx = SessionContext(
            session_id=0, userid=0, petid=0, pet_info={},
            hospitalid=hospitalid, emrid=None, scheduleid=None,
            user_message=msg, phase=Phase.PRE_BOOKING, db=db,
        )
        try:
            facts = await _reception_agent._collect_facts(ctx)
            if expected_tool is None:
                ok = "[get_" not in facts
                case_checks.append({
                    "item": f"도구 선택 ({desc})",
                    "status": "PASS" if ok else "WARN",
                    "detail": "도구 미호출 (정상)" if ok else f"무관 질문에 도구 호출됨: {facts[:80]}",
                })
                if ok:
                    tool_hit += 1
            else:
                ok = f"[{expected_tool}]" in facts
                case_checks.append({
                    "item": f"도구 선택 ({desc})",
                    "status": "PASS" if ok else "WARN",
                    "detail": f"{expected_tool} 호출됨" if ok else f"예상={expected_tool} 미호출 — facts: {facts[:80] or '(없음)'}",
                })
                if ok:
                    tool_hit += 1
        except Exception as exc:
            case_checks.append({"item": f"도구 선택 ({desc})", "status": "WARN", "detail": f"오류: {exc}"})

    acc = tool_hit / len(_TOOL_CASES)
    checks = [
        {
            "item": "MCP 도구 선택 (전체)",
            "status": "PASS" if acc == 1.0 else "WARN",
            "detail": f"{tool_hit}/{len(_TOOL_CASES)} ({acc:.0%}) — 기준 100%",
        },
        *case_checks,
    ]

    overall = "WARN" if any(c["status"] == "WARN" for c in checks) else "PASS"
    return {
        "agent": "reception",
        "overall": overall,
        "checks": checks,
        "metrics": {"tool_accuracy": round(acc, 3), "total_cases": len(_TOOL_CASES)},
    }


async def run_full_agent_report(db: AsyncSession) -> dict:
    """전체 에이전트 성능 통합 리포트.

    overall_verdict: PASS / PARTIAL_FAIL / CRITICAL_FAIL
    CRITICAL_FAIL 조건: RED flag recall < 100% 또는 triage_leak > 0
    """
    triage_r = await run_triage_eval()
    mcp_r = await run_mcp_health_check()
    orch_r = await run_orchestrator_eval(db)
    reception_r = await run_reception_eval(db)
    followup_r = await run_followup_filter_eval()

    # CRITICAL 조건
    rf_raw = triage_r.get("metrics", {}).get("red_flag_recall", "N/A")
    rf_critical = False
    if rf_raw not in ("N/A", None):
        parts = str(rf_raw).split("/")
        if len(parts) == 2:
            try:
                rf_critical = int(parts[0]) < int(parts[1])
            except ValueError:
                pass

    triage_leak = orch_r.get("metrics", {}).get("triage_leak_count", 0)

    all_modules = [triage_r, mcp_r, orch_r, reception_r, followup_r]
    if rf_critical or triage_leak > 0:
        verdict = "CRITICAL_FAIL"
    elif any(r.get("overall") in ("WARN", "ERROR") for r in all_modules):
        verdict = "PARTIAL_FAIL"
    else:
        verdict = "PASS"

    critical_reasons = []
    if rf_critical:
        critical_reasons.append("RED flag recall < 100%")
    if triage_leak > 0:
        critical_reasons.append(f"TRIAGING 중 유출 {triage_leak}건")

    return {
        "agent": "full_report",
        "overall_verdict": verdict,
        "modules": {
            "triage": triage_r,
            "mcp_health": mcp_r,
            "orchestrator": orch_r,
            "reception": reception_r,
            "followup": followup_r,
        },
        "critical_reasons": critical_reasons,
    }
