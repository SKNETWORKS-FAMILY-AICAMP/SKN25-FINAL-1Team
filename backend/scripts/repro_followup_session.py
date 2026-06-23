"""BOOKED(예약 후 followup 세션) 상태에서 보호자 메시지를 넣어
실제 오케스트레이터(run_turn)가 어떤 에이전트로 보내고 무슨 답을 내는지 재현.

스크린샷2 재현용: '집에서 수술하는 법' / '심판하는 표정 병인가요?' + 정상 경과 메시지.
DB 없이(SessionContext 직접 구성, db=None) 라우팅+노드 로직만 실제로 태운다.
LLM 키 있으면 실제 라우팅, 없으면 각 노드의 결정론 fallback이 찍힌다.

실행: python3 backend/scripts/repro_followup_session.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # backend/
sys.path.insert(0, str(HERE.parent.parent))   # repo root (ai.*)

import ai.orchestrator.graph as g  # noqa: E402
from ai.orchestrator.contracts import Flow, Phase, SessionContext  # noqa: E402

_routed = {"t": None}
_orig_route = g.route


async def _traced_route(ctx):
    t = await _orig_route(ctx)
    _routed["t"] = t
    return t


g.route = _traced_route


def _ctx(msg: str, attachments=None, history=None) -> SessionContext:
    return SessionContext(
        session_id=1, userid=1, petid=1, pet_info={"name": "뽀미", "species": "dog"},
        hospitalid=1, emrid=1, scheduleid=1,
        user_message=msg, attachments=attachments or [], history=history or [],
        phase=Phase.BOOKED, active_flow=Flow.IDLE, db=None,
    )


CASES = [
    "오늘 또 토했어요. 어제보다 더 처져 있어요.",   # 경과(증상 변화)
    "약 먹이고 나서는 좀 나아진 것 같아요.",         # 경과(약 반응)
    "병원 몇 시까지 해요?",                          # 병원 질문 → 응대
    "수의사 선생님 누구신지 알려주세요.",            # 병원/수의사 질문 → 응대
    "예약을 다른 날로 다시 잡고 싶어요.",            # 재예약 → followup_filter rebook_request
    "예약 시간 좀 바꿔주세요.",                      # 재예약 변형
    "더 빠른 시간 찾기",                             # 재예약 pill 클릭(결정론)
    "피를 토했어요. 계속 토하고 축 처져요.",          # urgent 경과 → 저장 + 재예약 pill 제안
    "강아지가 밥 먹을 때 심판하는 표정이에요. 병인가요?",  # 엉뚱/잡담
]


async def main():
    import os
    print(f"OPENAI_API_KEY set? {'yes' if os.getenv('OPENAI_API_KEY') else 'NO (→ fallback 경로)'}\n")
    for msg in CASES:
        _routed["t"] = None
        try:
            res = await g.run_turn(_ctx(msg))
            reply = (res.reply or "").replace("\n", " ")
            print(f"[보호자] {msg}")
            print(f"  → routed agent : {_routed['t']}")
            print(f"  → reply        : {reply}")
            print(f"  → quick_replies: {res.quick_replies}")
            print(f"  → events       : {[e.get('type') for e in (res.events or [])]}")
        except Exception as e:
            print(f"[보호자] {msg}\n  !! 예외: {type(e).__name__}: {e}")
        print("-" * 80)


if __name__ == "__main__":
    asyncio.run(main())
