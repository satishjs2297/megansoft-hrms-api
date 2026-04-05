import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import get_settings

settings = get_settings()
_lock = threading.Lock()
_buckets: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(bucket: str):
    max_per_minute = settings.heavy_rate_limit_per_minute
    if bucket == "login":
        max_per_minute = settings.login_rate_limit_per_minute

    async def dependency(request: Request):
        now = time.time()
        client = request.client.host if request.client else "unknown"
        key = f"{bucket}:{client}"
        with _lock:
            q = _buckets[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= max_per_minute:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            q.append(now)

    return dependency

