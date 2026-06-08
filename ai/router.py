"""AI 에이전트 FastAPI 라우터.

엔드포인트:
  POST /api/agent/run           → BackgroundTasks 에이전트 실행, task_id 반환
  GET  /api/agent/sse/{task_id} → SSE 실시간 진행 스트리밍

참고: vision CNN(피부/안구)은 챗봇 사진 업로드 흐름(chat.py)에서 vision_service를
직접 호출한다. 보호자 예약 흐름의 schedule 에이전트가 /run+/sse를 fallback으로 사용.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_current_user

router = APIRouter(prefix="/api/agent", tags=["AI 에이전트"])
logger = logging.getLogger(__name__)

# chat.py와 공유하는 태스크 스토어 (ai.tasks에서 단일 관리)
from ai.tasks import _task_store, cleanup_task_after_ttl, safe_create_task, TaskStatus


# ── BackgroundTasks 기반 에이전트 실행 ────────────────────────────
@router.post("/run")
async def run_agent(body: dict, background_tasks: BackgroundTasks, current_user=Depends(get_current_user)):
    """에이전트를 BackgroundTasks로 비동기 실행합니다. (인증된 보호자만)

    agent_type: triage | schedule | chart | validation | judge | followup
    """
    from ai.schemas import AGENT_TYPES

    agent_type = body.get("agent_type", "")
    if agent_type not in AGENT_TYPES:
        raise HTTPException(400, f"알 수 없는 에이전트 타입: {agent_type}")

    task_id = str(uuid.uuid4())
    _task_store[task_id] = {"status": "queued", "step": ""}

    background_tasks.add_task(
        _execute_agent,
        task_id,
        agent_type,
        body.get("payload", {}),
        body.get("emrid"),
        body.get("scheduleid"),
        body.get("user_id"),
    )
    return {"task_id": task_id, "agent_type": agent_type}


async def _execute_agent(
    task_id: str,
    agent_type: str,
    payload: dict,
    emrid: int | None,
    scheduleid: int | None,
    user_id: int | None,
) -> None:
    from ai.tasks import RUNNERS, save_result

    _task_store[task_id] = {"status": "running", "step": "시작 중..."}

    def update_step(step: str) -> None:
        if task_id in _task_store:
            _task_store[task_id]["step"] = step

    try:
        runner = RUNNERS.get(agent_type)
        if not runner:
            raise ValueError(f"Runner 없음: {agent_type}")

        result = await runner(payload, update_step, emrid, scheduleid)

        if user_id:
            await save_result(agent_type, result, emrid, scheduleid, user_id)

        _task_store[task_id] = {"status": TaskStatus.DONE, "result": result}
        logger.info("[Task] %s 완료 task_id=%s", agent_type, task_id)
    except Exception as exc:
        logger.error("[Task] %s 실패 task_id=%s: %s", agent_type, task_id, exc, exc_info=True)
        _task_store[task_id] = {"status": TaskStatus.ERROR, "detail": str(exc)}
    finally:
        # SSE가 미접속해도 5분 후 자동 정리 (SSE가 먼저 pop하면 no-op)
        safe_create_task(
            cleanup_task_after_ttl(task_id),
            name=f"cleanup:{task_id}",
        )


# ── SSE 실시간 스트리밍 ───────────────────────────────────────────
@router.get("/sse/{task_id}")
async def agent_sse(task_id: str, current_user=Depends(get_current_user)):
    """SSE로 에이전트 실행 결과를 스트리밍합니다.

    이벤트 형식:
      data: {"status": "running", "step": "증상 키워드 추출 중..."}
      data: {"status": "done", "result": {...}}
      data: {"status": "error", "detail": "..."}
    """
    async def event_stream():
        yield f"data: {json.dumps({'status': 'connecting', 'task_id': task_id})}\n\n"

        for _ in range(120):  # 최대 2분
            task = _task_store.get(task_id)
            if task is None:
                yield f"data: {json.dumps({'status': 'error', 'detail': 'task not found'})}\n\n"
                return

            status = task["status"]
            if status in ("queued", "running"):
                yield f"data: {json.dumps({'status': status, 'step': task.get('step', '')})}\n\n"
            elif status == "done":
                yield f"data: {json.dumps({'status': 'done', 'result': task.get('result')})}\n\n"
                _task_store.pop(task_id, None)
                return
            elif status == "error":
                yield f"data: {json.dumps({'status': 'error', 'detail': task.get('detail', '')})}\n\n"
                _task_store.pop(task_id, None)
                return

            await asyncio.sleep(1)

        _task_store.pop(task_id, None)
        yield f"data: {json.dumps({'status': 'timeout'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
