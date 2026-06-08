"""Judge Agent — 시스템 품질 모니터링 (환자 안전 검증 아님).

[포지셔닝 — 최종발표 기준]
Judge는 '환자 안전'이나 '의료적 정답'을 판정하지 않는다.
오직 AI 대화 시스템이 운영 품질 기준대로 작동하는지를 모니터링한다.

평가 항목 (운영 품질 지표):
  1. 문진 완전성   — 필수 항목을 대화로 잘 수집했는가
  2. 질문 효율성   — 불필요하게 많이 되묻지 않고 효율적으로 수집했는가
  3. 대화 턴 수    — (객관) 보호자 응답까지 걸린 턴 수
  4. 응답 일관성   — 대화 흐름과 구조화 결과가 논리적으로 일관되는가
  5. 구조화 품질   — 자연어를 구조화 데이터로 잘 변환했는가

활용: 운영 모니터링 목적. 결과는 audit log에만 남긴다(DB 저장 불필요).
독립 인스턴스로 호출해 self-enhancement 편향을 줄인다.
참고: Zheng et al. 2023, "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena" (NeurIPS).
(정책: JUDGE_POLICY.md)
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable

from .base import call_openai_once

logger = logging.getLogger(__name__)


def _count_turns(chat_history: list[dict]) -> int:
    """객관 지표: 보호자(user) 발화 턴 수 — 코드로 직접 계산(LLM 비의존)."""
    return sum(
        1 for m in chat_history
        if (m.get("role") == "user" or m.get("type") == "user")
        and (m.get("content") or m.get("text"))
    )


def build_judge_prompt(triage_result: dict | None, chat_history: list[dict]) -> str:
    history_text = "\n".join(
        f"[{'AI' if (m.get('type') == 'bot' or m.get('role') == 'assistant') else '보호자'}] "
        f"{m.get('text') or m.get('content', '')}"
        for m in chat_history
    ) or "(대화 기록 없음)"

    return f"""당신은 AI 대화 시스템의 '운영 품질 모니터링' 평가자입니다.
환자 안전이나 의료적 정답을 판단하지 마세요. 오직 AI가 보호자 자연어를 얼마나
효율적이고 일관되게 '구조화'했는지(운영 품질)만 평가합니다.

[평가 대상: 구조화 결과(triage가 추출한 구조화 데이터)]
{json.dumps(triage_result, ensure_ascii=False, indent=2)}

[평가 대상: 대화 기록]
{history_text}

[평가 항목 — 각 0~10, 운영 품질 관점]
1) 문진 완전성: 필수 항목(주증상·발현시점·증상키워드 등)을 대화로 수집했는가
2) 질문 효율성: 불필요한 반복 질문 없이 효율적으로 수집했는가
3) 응답 일관성: 대화 내용과 구조화 결과가 논리적으로 일관되는가
4) 구조화 품질: 보호자의 일상어를 구조화 필드로 적절히 변환했는가

[응답 형식 — JSON만 출력]
{{
  "quality_scores": {{
    "completeness": 8.5,
    "question_efficiency": 9.0,
    "response_consistency": 8.8,
    "structuring_quality": 8.0
  }},
  "monitoring_verdict": "HEALTHY 또는 NEEDS_REVIEW",
  "notes": "운영 품질 관점의 한두 문장 코멘트(의료 판단 금지)",
  "improvement_points": ["대화 설계 개선 제안 (없으면 빈 배열)"]
}}

monitoring_verdict 기준(운영 품질):
- HEALTHY: 네 점수 모두 7.0 이상
- NEEDS_REVIEW: 한 항목이라도 7.0 미만 (= 대화 설계/프롬프트 점검 대상, 환자 위험 신호 아님)"""


async def run_judge(
    payload: dict,
    update_step: Callable[[str], None],
    emrid: int | None,
    scheduleid: int | None,
) -> dict:
    """Judge Agent 실행 — 운영 품질 모니터링. 결과는 호출부에서 audit log로만 기록."""
    triage_result = payload.get("triage_result")
    chat_history = payload.get("chat_history", []) or []

    turn_count = _count_turns(chat_history)  # 객관 지표(코드 계산)

    update_step("운영 품질 모니터링 중...")
    try:
        result = await call_openai_once(
            "운영 품질을 평가하세요.",
            build_judge_prompt(triage_result, chat_history),
            max_tokens=800,
            agent="judge",
        )
        if not isinstance(result, dict):
            result = {}
    except Exception as exc:
        logger.warning(f"[Judge] LLM 실패 emrid={emrid}: {exc}")
        result = {"monitoring_verdict": "NEEDS_REVIEW", "notes": "모니터링 LLM 일시 오류"}

    result["turn_count"] = turn_count  # 객관 지표 병합

    logger.info(
        "[Judge] emrid=%s verdict=%s scores=%s turns=%s",
        emrid, result.get("monitoring_verdict"), result.get("quality_scores"), turn_count,
    )
    return {"agent": "judge", "emrid": emrid, **result}
