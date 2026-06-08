"""Triage Agent — 문진 대화 LLM 요약 노드.

라이브 트리아지(질문 생성·응급도 점수·red flag·off-tree RAG)는 ai.triage.engine + chat.py가
담당한다(결정론). 이 에이전트는 LangGraph triage_complete 그래프의 첫 노드로, 완료된 대화를
받아 SOAP의 S(주관적)에 해당하는 '한 줄 평서형' 요약을 LLM으로 생성한다.

응급도/키워드/red flag/의심질환은 엔진 결과(collected_info)를 그대로 유지하고,
symptom_summary만 LLM 요약으로 업그레이드한다(주요증상·의심질환은 명사형이므로 요약은 서술형).
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from .base import call_openai

logger = logging.getLogger(__name__)


def _format_conversation(messages: list[dict]) -> str:
    lines: list[str] = []
    for m in (messages or [])[-14:]:
        role = "보호자" if m.get("role") == "user" else "챗봇"
        content = " ".join(str(m.get("content") or "").split())
        if content:
            lines.append(f"{role}: {content[:300]}")
    return "\n".join(lines) or "(대화 없음)"


async def _llm_summary(messages: list[dict], collected_info: dict, pet: dict) -> str | None:
    """문진 대화를 SOAP S 한 줄(평서형 '~이다')로 요약. 실패 시 None."""
    animal = "고양이" if (pet.get("species") == "cat") else "강아지"
    convo = _format_conversation(messages)
    chief = collected_info.get("chief_complaint") or ""
    keywords = ", ".join(collected_info.get("symptom_keywords") or [])
    system = (
        f"너는 동물병원 트리아지 보조야. 아래 {animal} 문진 대화를 SOAP의 S(주관적)로 요약해.\n"
        f"주요 증상: {chief} / 키워드: {keywords}\n\n"
        "규칙: 보호자가 말한 내용만으로 '한 문장' 요약. 반드시 '~이다/~한다/~보인다' 같은 "
        "평서형 종결로 끝낼 것(명사 나열·존댓말 금지). 진단 단정 금지. 예: '오른쪽 뒷다리를 "
        "절며 통증을 보인다.'\n"
        'JSON만 출력: {"summary": "한 줄 요약"}'
    )
    try:
        result = await call_openai(
            [{"role": "user", "content": convo}],
            system,
            max_tokens=150,
            agent="triage",
        )
        if isinstance(result, dict):
            summary = str(result.get("summary") or "").strip()
            return summary or None
    except Exception as e:
        logger.warning(f"[Triage] 요약 생성 실패: {e}")
    return None


async def run_triage(
    payload: dict,
    update_step: Callable[[str], None],
    emrid: int | None,
    scheduleid: int | None,
) -> dict:
    """triage_complete 그래프의 요약 노드.

    payload: {messages: 대화, collected_info: 엔진 결과, pet: 펫정보}
    반환: {symptom_summary, collected_info(요약 갱신)} — 응급도 등은 엔진 결과 유지.
    """
    messages = payload.get("messages", [])
    collected_info = dict(payload.get("collected_info") or {})
    pet = payload.get("pet", {})

    update_step("문진 요약 생성 중...")
    summary = await _llm_summary(messages, collected_info, pet)
    if summary:
        collected_info["symptom_summary"] = summary

    logger.info(f"[Triage] emrid={emrid} summary_updated={bool(summary)}")
    return {
        "agent": "triage",
        "emrid": emrid,
        "symptom_summary": summary,
        "collected_info": collected_info,
    }
