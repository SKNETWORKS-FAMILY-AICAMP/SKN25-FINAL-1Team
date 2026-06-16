"""Judge 운영 모니터링 — DB 없이 최근 결과를 메모리에 보관(운영탭 표시용).

judge.py 설계대로 judge 결과는 audit log 성격이라 영속 DB가 필요 없다.
같은 백엔드 프로세스에서 에이전트(judge)가 record_judge로 적재하고,
운영자 API(/admin/judge/results)가 recent_judge로 읽는다. (프로세스 재시작 시 초기화 — 데모/모니터링 용도로 충분)
"""
from collections import deque
from datetime import datetime, timezone
from typing import Any

_MAXLEN = 200
_JUDGE_RESULTS: "deque[dict[str, Any]]" = deque(maxlen=_MAXLEN)


def record_judge(emrid: int | None, result: dict) -> None:
    """judge 1건을 최근 목록 맨 앞에 적재."""
    _JUDGE_RESULTS.appendleft({
        "emrid": emrid,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "verdict": result.get("monitoring_verdict"),
        "scores": result.get("quality_scores") or {},
        "turnCount": result.get("turn_count"),
        "notes": result.get("notes"),
    })


def recent_judge(needs_review_only: bool = False) -> list[dict]:
    """최근 judge 결과(최신순). needs_review_only=True면 NEEDS_REVIEW만."""
    items = list(_JUDGE_RESULTS)
    if needs_review_only:
        items = [r for r in items if r.get("verdict") == "NEEDS_REVIEW"]
    return items
