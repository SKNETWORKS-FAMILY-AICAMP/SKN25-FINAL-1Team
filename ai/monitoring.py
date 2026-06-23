"""에이전트 운영 모니터링 — 메모리 링버퍼.

서버 재시작 시 초기화됨 (DB 없이 최근 N건만 유지).
각 에이전트는 push_log(agent, entry)로 결과를 기록하면 됩니다.

사용 예:
    from ai.monitoring import push_log
    push_log("followup_filter", {"message": "...", "category": "symptom_change", ...})
    push_log("triage", {"message": "...", "urgency": "RED", ...})
"""
from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any

_MAX = 200  # 에이전트당 최대 보관 건수

# 에이전트명 → deque
_BUFFERS: dict[str, deque[dict[str, Any]]] = {}

# Judge 전용 버퍼 (기존 엔드포인트 호환)
_JUDGE_BUF: deque[dict[str, Any]] = deque(maxlen=_MAX)


def _buf(agent: str) -> deque[dict[str, Any]]:
    if agent not in _BUFFERS:
        _BUFFERS[agent] = deque(maxlen=_MAX)
    return _BUFFERS[agent]


def push_log(agent: str, entry: dict[str, Any]) -> None:
    """에이전트 실행 결과를 링버퍼에 기록.

    agent: "followup_filter" | "triage" | "schedule" | "chart" | "reception"
    entry: 에이전트별 자유 형식 dict — ts(타임스탬프)는 자동 추가됨
    """
    entry.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
    entry["agent"] = agent
    _buf(agent).appendleft(entry)


def recent_logs(agent: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """최근 로그 조회.

    agent 지정 시 해당 에이전트만, None이면 전체 에이전트 합산 후 시간 역순.
    """
    if agent:
        return list(_buf(agent))[:limit]

    all_logs: list[dict[str, Any]] = []
    for buf in _BUFFERS.values():
        all_logs.extend(buf)
    all_logs.sort(key=lambda x: x.get("ts", ""), reverse=True)
    return all_logs[:limit]


def log_stats(agent: str | None = None) -> dict[str, Any]:
    """에이전트별 간단 통계 (총 건수, 오류 건수, 최근 실행 시각)."""
    agents = [agent] if agent else list(_BUFFERS.keys())
    result = {}
    for a in agents:
        logs = list(_buf(a))
        result[a] = {
            "total": len(logs),
            "errors": sum(1 for l in logs if l.get("error")),
            "last_at": logs[0].get("ts") if logs else None,
        }
    return result


# ── Judge 호환 (기존 admin.py 엔드포인트 유지) ────────────────
def push_judge(entry: dict[str, Any]) -> None:
    entry.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
    _JUDGE_BUF.appendleft(entry)


def recent_judge(needs_review_only: bool = False) -> list[dict[str, Any]]:
    logs = list(_JUDGE_BUF)
    if needs_review_only:
        logs = [l for l in logs if l.get("verdict") == "NEEDS_REVIEW"]
    return logs
