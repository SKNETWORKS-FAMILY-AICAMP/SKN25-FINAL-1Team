"""Validation Agent — AI 산출물의 품질·안전성 검증 계층 (의료 진단 검증기가 아님).

[포지셔닝 — 최종발표 기준]
MediPaw는 의료 진단 AI가 아니라 소형 동물병원의 업무 효율화·골든타임 확보를 위한
"AI 업무 보조 시스템"이다. 따라서 Validation Agent는 의료적 정답 여부를 판정하지 않는다.
다음 4가지만 검증한다 — 모두 '판정'이 아니라 '신호 감지 / 누락 점검'이다:

  A. Data Completeness  — 필수 문진 5항목 누락 여부 (채워진 필드 ÷ 5)            [규칙·숫자]
  B. Workflow Consistency — 문진 증상 키워드의 차트 등장 비율 (일치율 < 50% 경고)  [규칙·숫자]
  C. Schedule Safety    — 예상 진료시간/예약 창 유효성                          [규칙·숫자]
  D. 응급신호 정합성     — 응급표현 사전 매칭 ↔ triage 응급도(Level) 불일치 여부   [규칙·숫자]

★ 전부 결정론적이다. **LLM(AI)을 쓰지 않는다.** 같은 입력이면 항상 같은 결과(재현 가능).
  → "AI가 AI를 검사한다"는 의심을 구조적으로 제거한다.
핵심: Validation은 "응급이다"를 판정하지 않는다. 최종 의료 판단은 수의사가 수행한다.
(정책: VALIDATION_POLICY.md)
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable

from ..observability import push_scores, score_trace

logger = logging.getLogger(__name__)


# ── A. 필수 문진 항목 (결정론적 누락 점검) ────────────────────────────────────
REQUIRED_FIELDS = {
    "species": "종",
    "age": "나이",
    "gender": "성별",
    "chief_complaint": "주증상",
    "symptom_onset": "발현 시점",
}


# ── D. Red Flag 표현 사전 (보호자 일상어 기준, 결정론적 탐지) ──────────────────
# 의학적 '진단'이 아니라, 응급 가능성을 시사하는 '표현'을 감지하기 위한 키워드 사전.
# 보호자가 의료용어를 쓰지 않으므로 일상 표현 위주로 구성한다.
RED_FLAG_LEXICON: dict[str, list[str]] = {
    "호흡 곤란 신호": ["숨을 못", "숨을 안", "숨쉬기", "숨이 차", "호흡곤란", "헐떡", "청색", "혀가 파", "잇몸이 파"],
    "의식 저하 신호": ["의식이 없", "의식 없", "반응이 없", "반응 없", "쓰러", "기절", "축 늘어", "정신을 잃"],
    "경련 지속 신호": ["경련", "발작", "경기", "떨면서", "몸을 떨"],
    "다량 출혈 신호": ["피를 많이", "출혈이 심", "피가 멈추지", "토혈", "각혈", "혈변", "코피가 멈"],
    "중독/이물 신호": ["삼켰", "먹으면 안", "중독", "초콜릿", "양파", "포도", "쥐약", "농약"],
    "쇼크 의심 신호": ["잇몸이 하얗", "몸이 차갑", "체온이 낮", "축 처져"],
}


def _scan_red_flags(text: str) -> list[str]:
    """문진 텍스트에서 사전 정의된 응급 신호 '표현'을 탐지한다(판정 아님, 감지만)."""
    found: list[str] = []
    for category, phrases in RED_FLAG_LEXICON.items():
        if any(p in text for p in phrases):
            found.append(category)
    return found


def _check_completeness(pet: dict, triage: dict) -> dict:
    """A. 필수 문진 항목 누락 점검 — 규칙 기반(필드 존재 여부)."""
    present = {
        "species": pet.get("species"),
        "age": pet.get("age"),
        "gender": pet.get("gender"),
        "chief_complaint": triage.get("chief_complaint"),
        "symptom_onset": triage.get("symptom_onset"),
    }
    missing = [
        label for key, label in REQUIRED_FIELDS.items()
        if present.get(key) in (None, "", "?", "미상", "알 수 없음")
    ]
    return {
        "status": "PASS" if not missing else "WARN",
        "missing_fields": missing,
        "detail": "필수 문진 정보 모두 수집됨" if not missing
        else f"누락 항목: {', '.join(missing)}",
    }


def _check_schedule_safety(schedule_result: dict) -> dict:
    """C. 예약 안전성 점검 — 규칙 기반(시간/슬롯 메타데이터)."""
    duration = schedule_result.get("estimated_duration_min")
    slot_window = schedule_result.get("slot_window")
    issues: list[str] = []
    if not duration or duration <= 0:
        issues.append("예상 진료시간이 산정되지 않음")
    if not slot_window:
        issues.append("예약 창(slot_window)이 비어 있음")
    return {
        "status": "PASS" if not issues else "WARN",
        "detail": "예약 메타데이터 정상" if not issues else "; ".join(issues),
    }


def _collect_symptom_text(triage: dict) -> str:
    """Red Flag 스캔 대상이 되는 문진 텍스트를 합친다."""
    parts = [
        triage.get("chief_complaint") or "",
        triage.get("symptom_summary") or "",
        " ".join(triage.get("symptom_keywords") or []),
        " ".join(triage.get("red_flags") or []),
    ]
    return " ".join(parts)


# ── 운영 검토 알림 임계값 (의학 기준 아님 · 튜닝 가능 · 근거는 VALIDATION_POLICY.md §3) ──
# 매직넘버가 아니라 '검토 알림'을 띄울지 정하는 명명 상수다. 판정이 아니므로 임상 검증 대상이 아니며,
# 병원별 오탐 허용치에 맞춰 조정할 수 있다. 패널에 계산 근거("일치율 X% < 50%")가 그대로 노출된다.
CHART_OVERLAP_THRESHOLD = 0.5   # 문진 증상 키워드의 차트 등장 비율이 이 미만이면 '문진-차트 불일치' 알림
LOW_URGENCY_THRESHOLD = 4       # triage urgency_level_num ≥ 4(표시상 '일반')면 '낮음'으로 보고 응급표현과의 불일치 알림


def _check_workflow_consistency(triage: dict, chart_result: dict | None) -> dict:
    """B. 문진 ↔ 차트 일치도 — **결정론적 키워드 일치율** (LLM 미사용).

    의학적 정답을 판단하지 않는다. "문진에서 보고된 증상 키워드가 AI 차트 본문에
    실제로 등장하는가"라는 **표면적 커버리지**만 문자열 매칭으로 측정한다.
    같은 입력이면 항상 같은 결과(재현 가능).
    """
    keywords = [k for k in (triage.get("symptom_keywords") or []) if k]
    if not chart_result:
        return {"status": "SKIPPED", "detail": "차트 초안이 아직 없어 일치도 점검을 건너뜀"}
    if not keywords:
        return {"status": "SKIPPED", "detail": "문진 증상 키워드가 없어 일치도 점검 불가"}

    chart_text = json.dumps(chart_result, ensure_ascii=False)
    matched = [k for k in keywords if k in chart_text]
    overlap = len(matched) / len(keywords)
    pct = int(round(overlap * 100))
    status = "PASS" if overlap >= CHART_OVERLAP_THRESHOLD else "WARN"
    detail = (
        f"문진 증상 {len(keywords)}개 중 차트 언급 {len(matched)}개 (일치율 {pct}%, 기준 {int(CHART_OVERLAP_THRESHOLD*100)}%↑)"
        if status == "PASS"
        else f"문진 증상 {len(keywords)}개 중 차트 언급 {len(matched)}개뿐 (일치율 {pct}% < {int(CHART_OVERLAP_THRESHOLD*100)}%) — 문진-차트 불일치 의심, 확인 권고"
    )
    return {"status": status, "overlap_pct": pct, "matched": matched, "detail": detail}


def normalize_validation(raw: dict) -> dict:
    """검증 결과를 DB(validation_result) 컬럼 매핑과 호환되는 형태로 정규화."""
    cats = raw  # 이미 조립된 dict
    checks = [
        {"item": "데이터 완전성", "status": cats["data_completeness"]["status"], "detail": cats["data_completeness"]["detail"]},
        {"item": "문진-차트 일치도", "status": cats["workflow_consistency"]["status"], "detail": cats["workflow_consistency"]["detail"]},
        {"item": "예약 안전성", "status": cats["schedule_safety"]["status"], "detail": cats["schedule_safety"]["detail"]},
        # Red Flag는 '응급도와 불일치'일 때만 WARN (감지+응급도 일치는 PASS=중복 제거).
        {"item": "응급신호 정합성", "status": cats["red_flag_detection"]["status"], "detail": cats["red_flag_detection"]["detail"]},
    ]
    # completeness만 객관적 점수(수집 필드 비율)로 환산 — 의료적 점수가 아님.
    total = len(REQUIRED_FIELDS)
    missing_n = len(cats["data_completeness"]["missing_fields"])
    completeness_ratio = round((total - missing_n) / total * 10, 1)
    return {
        **cats,
        "overall": cats["overall"],
        "checks": checks,
        # accuracy/consistency 등 '의료적 점수'는 의도적으로 산정하지 않는다(None).
        "scores": {"completeness": completeness_ratio},
        "summary": cats["summary"],
    }


async def run_validation(
    payload: dict,
    update_step: Callable[[str], None],
    emrid: int | None,
    scheduleid: int | None,
) -> dict:
    """Validation Agent 실행 — 대부분 규칙 기반, B(일관성)만 LLM 보조."""
    pet = payload.get("pet", {})
    triage = payload.get("triage_result") or payload.get("triage_info") or {}
    schedule_result = payload.get("schedule_result") or payload.get("schedule_slot") or {}
    chart_result = payload.get("chart_result")

    # A. Data Completeness (규칙)
    update_step("필수 문진 정보 점검 중...")
    completeness = _check_completeness(pet, triage)

    # C. Schedule Safety (규칙)
    schedule_safety = _check_schedule_safety(schedule_result)

    # D. Red Flag ↔ 응급도 '불일치' 점검 (규칙)
    # 응급표현이 감지됐는데 triage가 낮게(Level ≥ 4) 평가했을 때만 경고한다.
    # (감지 + 응급도도 높음 → 두 신호가 일치 → 배지로 충분하므로 경고하지 않음 = 중복 제거)
    update_step("응급 신호 ↔ 응급도 정합성 점검 중...")
    signals = _scan_red_flags(_collect_symptom_text(triage))
    try:
        urgency_num = int(triage.get("urgency_level_num") or 5)
    except (TypeError, ValueError):
        urgency_num = 5
    disagree = bool(signals) and urgency_num >= LOW_URGENCY_THRESHOLD
    red_flag = {
        "detected": bool(signals),
        "signals": signals,
        "urgency_level_num": urgency_num,
        "status": "WARN" if disagree else "PASS",
        "detail": (
            f"응급 신호 표현({', '.join(signals)}) 감지됐으나 triage 응급도 Level {urgency_num}(낮음) — "
            f"AI가 응급도를 낮게 봤을 수 있어 재확인 권고"
            if disagree else
            (f"응급 신호 표현 감지({', '.join(signals)}) — 응급도 Level {urgency_num}와 일치"
             if signals else "사전 정의된 응급 신호 표현 미감지")
        ),
    }

    # B. Workflow Consistency (결정론적 키워드 일치율 — LLM 미사용)
    update_step("문진-차트 일치도 점검 중...")
    consistency = _check_workflow_consistency(triage, chart_result)

    # 종합: 수의사가 '문진만 봐선 모를 예외'가 하나라도 있으면 ATTENTION.
    needs_attention = (
        completeness["status"] == "WARN"
        or schedule_safety["status"] == "WARN"
        or consistency.get("status") == "WARN"
        or red_flag["status"] == "WARN"
    )
    overall = "ATTENTION" if needs_attention else "OK"

    summary_bits = []
    if completeness["status"] == "WARN":
        summary_bits.append("필수 문진 정보 누락")
    if consistency.get("status") == "WARN":
        summary_bits.append("문진-차트 불일치 의심")
    if schedule_safety["status"] == "WARN":
        summary_bits.append("예약 메타데이터 점검 필요")
    if red_flag["status"] == "WARN":
        summary_bits.append("응급 신호 ↔ 응급도 불일치")
    summary = "수의사 검토 권고: " + ", ".join(summary_bits) if summary_bits else "특이 검증 이슈 없음"

    assembled = {
        "overall": overall,
        "data_completeness": completeness,
        "workflow_consistency": consistency,
        "schedule_safety": schedule_safety,
        "red_flag_detection": red_flag,
        "summary": summary,
    }
    result = normalize_validation(assembled)

    # Langfuse 점수 — 규칙 검증 결과를 대시보드에서 추세로 확인(LLM 미사용이라 standalone trace).
    with score_trace("validation"):
        push_scores(
            numeric={
                "validation.completeness": result["scores"].get("completeness"),
                "validation.chart_overlap_pct": consistency.get("overlap_pct"),
            },
            categorical={
                "validation.overall": overall,
                "validation.data_completeness": completeness["status"],
                "validation.workflow_consistency": consistency.get("status"),
                "validation.schedule_safety": schedule_safety["status"],
                "validation.red_flag": red_flag["status"],
            },
        )

    logger.info(
        "[Validation] emrid=%s overall=%s redflag=%s missing=%s",
        emrid, overall, signals, completeness["missing_fields"],
    )
    return {"agent": "validation", "emrid": emrid, "scheduleid": scheduleid, **result}
