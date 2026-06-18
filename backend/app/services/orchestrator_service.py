"""챗봇 한 턴 처리 — v2 오케스트레이터 진입점.

chat.py(send_message)가 이걸 호출한다.
흐름: 세션 로드 → 사용자 메시지 저장 → SessionContext 만들기 → run_turn(지휘자)
      → 상태 저장(orch_state) → 어시스턴트 메시지 저장 → 결과 이벤트 yield
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def process_turn(db, session_id: int, userid: int, request):
    from app.crud.chat import add_message, get_chat_session

    from ai.orchestrator.graph import run_turn
    from ai.orchestrator.state import apply_patch, build_context, save_state

    session = await get_chat_session(db, session_id, userid)
    if not session:
        raise ValueError("상담 세션을 찾을 수 없습니다.")

    content = request.content
    image_url = request.image_url
    attachments = [image_url] if image_url else []

    # 1) 사용자 메시지 저장
    await add_message(db, session, "user", content, image_url=image_url)

    # 2) 현재 상황(SessionContext) 만들기 + 한 턴 실행
    ctx = await build_context(db, session, content, attachments)
    result = await run_turn(ctx)

    # 3) 바뀐 상태 저장 (orch_state)
    apply_patch(ctx, result.state_patch)
    await save_state(db, ctx)

    # 4) 챗봇 답 저장 (재진입 시 pill 복원용 meta)
    await add_message(db, session, "assistant", result.reply,
                      meta={"quick_replies": result.quick_replies})

    # 5) 프론트로 보낼 결과
    payload = {
        "reply": result.reply,
        "quick_replies": result.quick_replies,
        "is_complete": False,
        "emrid": session.emrid,
    }
    for ev in (result.events or []):
        if ev.get("type") == "triage_complete":
            data = ev.get("data") or {}
            payload.update({
                "is_complete": True,
                "emrid": ev.get("emrid"),
                "urgency": data.get("urgency"),
                "chief_complaints": data.get("chief_complaints") or [],
                "suspected_conditions": data.get("suspected_conditions") or [],
                "triage_summary": data.get("triage_summary"),
                "keywords": data.get("symptom_keywords") or [],
            })

    yield {"type": "result", "result": payload}
