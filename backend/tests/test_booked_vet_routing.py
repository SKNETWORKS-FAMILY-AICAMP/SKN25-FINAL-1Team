from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.orchestrator.contracts import Phase, SessionContext
from ai.orchestrator.router import route


def _ctx(message: str) -> SessionContext:
    return SessionContext(
        session_id=1,
        userid=1,
        petid=1,
        pet_info={"name": "테스트펫"},
        hospitalid=1,
        emrid=10,
        scheduleid=20,
        user_message=message,
        phase=Phase.BOOKED,
    )


def test_booked_vet_questions_route_to_followup_filter():
    messages = [
        "나 누구한테 진료받아?",
        "담당 수의사 누구야?",
        "내 예약 의사 누구야?",
        "어떤 선생님이 봐줘?",
        "그 선생님 친절해?",
    ]
    for message in messages:
        assert asyncio.run(route(_ctx(message))) == "followup_filter"
