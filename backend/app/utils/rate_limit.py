"""아주 가벼운 인메모리 IP 레이트리미터.

공개(무인증) 엔드포인트(입점 신청·presigned 발급)의 남용을 막는 최소 장치.
단일 백엔드 컨테이너 기준 프로세스 메모리에 카운트한다.
※ 다중 인스턴스로 확장하면 Redis 등 공유 저장소로 교체해야 한다(현재는 단일 컨테이너).
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

# bucket_id("key:ip") → 최근 요청 시각(monotonic) 큐
_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    # nginx 뒤에 있으므로 X-Forwarded-For 의 첫 IP 를 우선 사용한다.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request, *, key: str, limit: int, window_sec: int) -> None:
    """key+IP 기준 window_sec 내 호출이 limit 을 넘으면 429 를 던진다."""
    now = time.monotonic()
    cutoff = now - window_sec
    bucket_id = f"{key}:{_client_ip(request)}"
    bucket = _BUCKETS[bucket_id]
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if not bucket:
        # 비어버린 버킷은 메모리 누수 방지를 위해 제거(곧 아래에서 다시 만들어짐).
        _BUCKETS.pop(bucket_id, None)
        bucket = _BUCKETS[bucket_id]
    if len(bucket) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요.",
        )
    bucket.append(now)
