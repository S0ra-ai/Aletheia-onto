"""Rate limiting middleware for production safety.

Prevents abuse and ensures fair usage of the platform APIs.
Uses an in-memory sliding window counter (suitable for single-process deployments).
"""

from __future__ import annotations

import time
from collections import defaultdict
from functools import wraps
from typing import Callable

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class RateLimiter:
    """In-memory rate limiter with sliding window."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed."""
        now = time.time()
        window_start = now - self.window_seconds

        # Clean old requests
        self.requests[key] = [t for t in self.requests[key] if t > window_start]

        if len(self.requests[key]) >= self.max_requests:
            return False

        self.requests[key].append(now)
        return True

    def get_remaining(self, key: str) -> int:
        """Get remaining requests in current window."""
        now = time.time()
        window_start = now - self.window_seconds
        current = len([t for t in self.requests[key] if t > window_start])
        return max(0, self.max_requests - current)


# Global rate limiter instance
_default_limiter = RateLimiter(max_requests=100, window_seconds=60)
_admin_limiter = RateLimiter(max_requests=20, window_seconds=60)  # Stricter for admin


def rate_limit(limiter: RateLimiter = _default_limiter):
    """Decorator for rate-limited endpoints."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request: Request = kwargs.get("request") or args[0]
            client_ip = request.client.host if request.client else "unknown"
            key = f"{client_ip}:{func.__name__}"

            if not limiter.is_allowed(key):
                raise HTTPException(
                    status_code=429, detail=f"请求过于频繁，请稍后再试。剩余时间: {limiter.window_seconds}s"
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


async def rate_limit_middleware(request: Request, call_next):
    """FastAPI middleware for rate limiting."""
    # Skip rate limiting for health checks
    if request.url.path in ["/health", "/metrics", "/docs", "/openapi.json"]:
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{request.url.path}"

    if not _default_limiter.is_allowed(key):
        return JSONResponse(
            status_code=429,
            content={"detail": "请求过于频繁，请稍后再试。", "retryAfter": _default_limiter.window_seconds},
        )

    response = await call_next(request)

    # Add rate limit headers
    response.headers["X-RateLimit-Limit"] = str(_default_limiter.max_requests)
    response.headers["X-RateLimit-Remaining"] = str(_default_limiter.get_remaining(key))
    response.headers["X-RateLimit-Reset"] = str(int(time.time()) + _default_limiter.window_seconds)

    return response
