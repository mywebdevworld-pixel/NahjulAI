"""Minimal in-memory per-IP sliding-window rate limiter.

Suitable for a single-process deployment (the free-tier target). For
multi-replica deployments swap this for a shared store (e.g. Redis).
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._last_sweep = 0.0

    def check(self, request: Request) -> None:
        """Raise 429 if the caller exceeded the limit."""
        # Respect proxy headers (HF Spaces / Render sit behind one).
        forwarded = request.headers.get("x-forwarded-for")
        ip = forwarded.split(",")[0].strip() if forwarded else (
            request.client.host if request.client else "unknown")

        now = time.monotonic()
        hits = self._hits[ip]
        cutoff = now - self.window_seconds
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= self.max_requests:
            retry_after = int(hits[0] + self.window_seconds - now) + 1
            raise HTTPException(
                status_code=429,
                detail="Too many requests — please slow down.",
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)

        # Periodically drop idle IPs so memory stays bounded.
        if now - self._last_sweep > self.window_seconds * 10:
            self._last_sweep = now
            stale = [k for k, v in self._hits.items() if not v or v[-1] < cutoff]
            for k in stale:
                del self._hits[k]


chat_limiter = RateLimiter(max_requests=10, window_seconds=60)
search_limiter = RateLimiter(max_requests=30, window_seconds=60)
