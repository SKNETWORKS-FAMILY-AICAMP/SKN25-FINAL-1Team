"""Booking Orchestration Agent — MCP 툴을 LLM tool-use로 엮어 예약 슬롯을 제안.

이 프로젝트의 'MCP 기반 업무 자동화' 핵심 결과물. 트리아지 응급도를 받아
MCP 서버의 find_open_slots(필요시 search_triage_cases)를 'MCP 프로토콜로' 호출해
가장 빠른 적합 슬롯을 찾고, 보호자용 제안 메시지를 만든다.

안전 원칙:
  - 제안만 한다. 실제 예약 확정(락·overlap 제약)은 하지 않는다 → 사람이 슬롯을 골라 확정.
  - 제시 슬롯은 LLM이 지어내지 않고, find_open_slots 툴 결과(실제 DB)를 그대로 쓴다.
"""
from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from ..mcp_client import call_tool, list_tool_schemas

logger = logging.getLogger(__name__)

# 에이전트에 노출할 MCP 툴(디버그용 preview_expanded_query 는 제외)
_AGENT_TOOLS = {"find_open_slots", "search_triage_cases"}
_MAX_TOOL_ROUNDS = 4
# 항상 정확히 N개의 슬롯을 제안한다. LLM이 limit 을 다르게 넘겨도 코드에서 덮어써 보장.
_SLOT_COUNT = 3


def _build_system_prompt() -> str:
    return (
        "당신은 MediPaw 예약 오케스트레이션 AI입니다. 트리아지 응급도에 맞춰 '가장 빠른'\n"
        "적합 진료 슬롯을 찾아 보호자에게 제안합니다.\n\n"
        "[도구 사용 — 반드시 MCP 툴로]\n"
        "- find_open_slots(urgency_level_num, duration_min, limit): 응급도에 맞는 가장 빠른\n"
        "  빈 슬롯을 조회. 급할수록(응급=1) 더 이른 시간이 나옵니다. 반드시 이 툴로 슬롯을 얻으세요.\n"
        "- search_triage_cases: 유사 사례가 진료 소요시간 판단에 도움될 때만 선택적으로 사용.\n\n"
        "[진료 소요시간(duration_min) 가이드]\n"
        "  응급도 Level 1~2 → 40, Level 3 → 30, Level 4~5 → 20 (분). 초진/복잡 증상이면 +10.\n\n"
        "[규칙]\n"
        "- 슬롯 시간은 절대 지어내지 말 것. find_open_slots 결과만 사용.\n"
        "- 진단·질환 추정·경중 판단 금지. 강한 어조('응급입니다' 등) 금지.\n"
        "- 슬롯을 확보했으면 짧은 제안 메시지를 쓰고 종료(추가 툴 호출 금지).\n\n"
        "[최종 출력 — JSON만]\n"
        '{"message": "보호자용 제안 한두 문장(가장 빠른 시간 안내, 진단 금지)",\n'
        ' "reasoning": "내부용: 응급도→duration→슬롯 선택 근거 한 문장"}'
    )


def _build_user_prompt(pet: dict, triage_info: dict) -> str:
    return (
        f"[반려동물] {pet.get('name')} / {pet.get('species','?')} / "
        f"{pet.get('age','?')}세 / {pet.get('weight','?')}kg\n"
        f"[트리아지] 응급도 num={triage_info.get('urgency_level_num')} "
        f"({triage_info.get('urgency_level','?')}) / 초진={triage_info.get('is_initial_visit', True)}\n"
        f"주증상: {triage_info.get('chief_complaint','')}\n"
        f"증상 키워드: {', '.join(triage_info.get('symptom_keywords') or [])}\n"
        f"증상 요약: {triage_info.get('symptom_summary','')}\n\n"
        "이 환자에게 가장 빠른 적합 슬롯을 find_open_slots 로 찾아 제안하세요."
    )


async def run_booking_orchestration(pet: dict, triage_info: dict) -> dict:
    """MCP tool-use 루프로 슬롯을 제안한다.

    Returns: {
      "proposed_slots": [...],   # find_open_slots 실제 결과(LLM이 지어낸 것 아님)
      "message": "...",          # 보호자용 제안
      "reasoning": "...",        # 내부 근거
      "tool_calls": [...],       # 어떤 MCP 툴을 호출했는지(관측용)
    }
    """
    from app.core.config import settings

    tool_schemas = [
        s for s in await list_tool_schemas()
        if s["function"]["name"] in _AGENT_TOOLS
    ]

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    model = settings.OPENAI_MODEL or "gpt-4o-mini"
    messages: list[dict] = [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": _build_user_prompt(pet, triage_info)},
    ]

    proposed_slots: list[dict] = []
    tool_calls_log: list[str] = []

    for _ in range(_MAX_TOOL_ROUNDS):
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tool_schemas,
            tool_choice="auto",
            max_completion_tokens=600,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            # 최종 답변 — JSON 파싱(실패해도 슬롯/메시지는 보존)
            parsed: dict = {}
            try:
                content = (msg.content or "").strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                parsed = json.loads(content) if content else {}
            except (json.JSONDecodeError, TypeError):
                parsed = {"message": (msg.content or "").strip()}
            return {
                "agent": "booking",
                "proposed_slots": proposed_slots,
                "message": parsed.get("message") or "가장 빠른 예약 가능 시간을 찾았어요. 아래에서 선택해 주세요.",
                "reasoning": parsed.get("reasoning"),
                "tool_calls": tool_calls_log,
            }

        # tool_calls 처리 — MCP 로 실제 호출
        messages.append(msg.model_dump())
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            # 슬롯 개수는 LLM 재량에 맡기지 않고 항상 _SLOT_COUNT 개로 고정.
            if name == "find_open_slots":
                args["limit"] = _SLOT_COUNT
            tool_calls_log.append(name)
            try:
                result = await call_tool(name, args)
            except Exception as exc:  # noqa: BLE001 — 툴 실패는 빈 결과로 LLM에 전달
                logger.warning("[Booking] MCP 툴 %s 실패: %s", name, exc)
                result = {"error": str(exc)}
            if name == "find_open_slots" and isinstance(result, dict):
                proposed_slots = result.get("slots") or proposed_slots
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    # 루프 한도 초과 — 확보한 슬롯이라도 반환
    logger.warning("[Booking] tool-use 라운드 한도 초과 (slots=%d)", len(proposed_slots))
    return {
        "agent": "booking",
        "proposed_slots": proposed_slots,
        "message": "가장 빠른 예약 가능 시간을 찾았어요. 아래에서 선택해 주세요.",
        "reasoning": "tool round limit",
        "tool_calls": tool_calls_log,
    }
