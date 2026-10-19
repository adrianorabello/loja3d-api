import time
from collections import defaultdict, deque
from typing import Deque, Dict
from fastapi import HTTPException, Request, status
from app.config import settings

_hits: Dict[str, Deque[float]] = defaultdict(deque)


def reset_rate_limits() -> None:
    _hits.clear()


def rate_limit(name: str, limit: int, window_seconds: int):
    """Per-client sliding window limiter (in memory; use a shared store with several workers)."""
    async def dependency(request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        client = request.client.host if request.client else "unknown"
        key = f"{name}:{client}"
        now = time.monotonic()
        hits = _hits[key]
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            retry_after = max(1, int(window_seconds - (now - hits[0])))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiadas tentativas. Tente novamente mais tarde.",
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)

    return dependency
