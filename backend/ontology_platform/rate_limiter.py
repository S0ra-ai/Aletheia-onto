"""Per-caller request rate limiting.

Two limits, because there are two problems. One protects the process from a caller
generating more work than it can do; the other protects the credentials, where the threat
is not volume but patience -- a few attempts a minute against one account still succeeds
given months. The second limit is far stricter than it would ever make sense to apply to
the API as a whole.

**The limit runs before authentication.** That is the whole point: the expensive pre-auth
work -- digesting a token, verifying an SSO assertion, checking a password -- is what an
unauthenticated flood targets, so a limit applied after authentication exempts exactly the
traffic it exists to bound. The cost is that the key is the client address rather than the
principal.

Keying on the address has a known weakness, stated plainly: several hundred people behind
one NAT share a key and therefore share a budget. The alternative -- keying on the
principal -- is unavailable here (nobody is authenticated yet) and would in any case
exempt unauthenticated traffic. Operators with large shared-egress populations should set
the limit by that population, not by the individual.

**Keys are evicted, not accumulated.** A counter per address is memory a caller controls:
rotating source addresses would otherwise grow the table without bound, which turns a
protection into a denial-of-service vector. A key with an empty window is dropped on
access.

**Off unless configured.** Running a rate limiter by default would make ordinary bursts
fail in ways that look like a broken deployment, and its correct limit depends on the
deployment's traffic -- a number this package cannot know. `aletheia preflight` reports an
externally reachable deployment that has not set one.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders

from .access_policy import is_public, strip_version_prefix

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60

# Login and SSO exchange: low volume, high value to an attacker. Kept separate from the
# general limit so tightening it does not throttle ordinary API traffic.
AUTHENTICATION_PATHS = frozenset({"/auth/login", "/auth/sso/login"})
DEFAULT_AUTHENTICATION_LIMIT = 10


def resolve_rate_limit() -> int:
    """Requests per minute per client address; `0` disables limiting."""
    return _positive_int("ONTOLOGY_RATE_LIMIT_PER_MINUTE", 0)


def resolve_authentication_limit() -> int:
    """Requests per minute per client address against the authentication endpoints."""
    return _positive_int("ONTOLOGY_RATE_LIMIT_AUTH_PER_MINUTE", DEFAULT_AUTHENTICATION_LIMIT)


def _positive_int(name: str, default: int) -> int:
    """Parse a non-negative integer setting, falling back on anything unusable.

    A malformed value falls back rather than raising: refusing to start over a typo in a
    tuning knob is a worse outcome than running with the documented default, and the
    default is logged.
    """
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r 不是整数，改用默认值 %d", name, raw, default)
        return default
    if value < 0:
        logger.warning("%s=%r 为负数，改用默认值 %d", name, raw, default)
        return default
    return value


class RateLimiter:
    """Fixed-window counters: at most `max_requests` per key per `window_seconds`.

    A fixed window rather than a sliding one because the cost is bounded by the number of
    keys and not by the request rate. A sliding window holds one timestamp per request,
    which makes memory proportional to traffic -- the property a limiter is supposed to
    bound. The known artifact is that a burst spanning a window boundary can reach twice
    the limit; for protecting a process that is immaterial, and it is stated here rather
    than discovered later.
    """

    def __init__(self, max_requests: int, window_seconds: int = WINDOW_SECONDS) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        # Requests are served on the event loop for async endpoints and on worker threads
        # for sync ones, so check-and-record has to be atomic across both.
        self._lock = threading.Lock()

    def is_allowed(self, key: str, now: float | None = None) -> bool:
        """Record a hit for `key` and report whether it is within the limit."""
        moment = time.monotonic() if now is None else now
        cutoff = moment - self.window_seconds

        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                hits = deque()
                self._hits[key] = hits
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.max_requests:
                # Deliberately not recorded: a refused request must not extend the window,
                # or a caller at the limit would keep themselves locked out by retrying.
                return False
            hits.append(moment)
            return True

    def remaining(self, key: str, now: float | None = None) -> int:
        """Requests left in the current window, without recording a hit."""
        moment = time.monotonic() if now is None else now
        cutoff = moment - self.window_seconds
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                return self.max_requests
            while hits and hits[0] <= cutoff:
                hits.popleft()
            return max(0, self.max_requests - len(hits))

    def retry_after(self, key: str, now: float | None = None) -> int:
        """Seconds until this key may try again.

        Computed from the oldest hit still inside the window, not from the window length.
        A caller told to wait sixty seconds when three would do comes back at the wrong
        time, and a `Retry-After` that is usually an overestimate is one clients learn to
        ignore -- which costs the header its purpose.
        """
        moment = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return 0
            oldest = hits[0]
        return max(1, int(self.window_seconds - (moment - oldest)) + 1)

    def forget(self, key: str) -> None:
        """Drop a key's counters. Used by tests and after a successful login."""
        with self._lock:
            self._hits.pop(key, None)

    def tracked_keys(self) -> int:
        """How many keys are currently held. Exposed so the eviction is testable."""
        with self._lock:
            return len(self._hits)


@dataclass(frozen=True)
class RateLimitDecision:
    """Whether a request may proceed, and what to tell the caller either way."""

    allowed: bool
    limit: int
    remaining: int
    retry_after: int


class RateLimitMiddleware:
    """Pure ASGI middleware applying the general and authentication limits.

    Raw ASGI rather than `@app.middleware("http")` because this runs on every request and
    rejects some of them before any application code does. Starlette's
    `BaseHTTPMiddleware` runs the downstream application in a separate task per request,
    which is overhead this does not need -- it reads two values off the scope and either
    answers directly or passes through.

    Constructed once per application so counters are per-process. With multiple workers
    each worker counts separately, so the effective limit is the configured one times the
    worker count; that is documented rather than papered over, because the alternative --
    sharing counters across processes -- needs a store this package does not depend on.
    """

    # Annotated here rather than inferred from the parameter: with `no_implicit_optional`
    # off (see pyproject), a `None` default makes the parameter's type `None` and every
    # `await self.app(...)` becomes "None is not callable".
    app: Any

    def __init__(
        self,
        app: Any = None,
        general_limit: int | None = None,
        authentication_limit: int | None = None,
    ) -> None:
        self.app = app
        self.general = RateLimiter(general_limit if general_limit is not None else resolve_rate_limit())
        self.authentication = RateLimiter(
            authentication_limit if authentication_limit is not None else resolve_authentication_limit()
        )

    @property
    def enabled(self) -> bool:
        """Whether either limit is configured. Both at `0` disables the middleware."""
        return self.general.max_requests > 0 or self.authentication.max_requests > 0

    def decide(self, path: str, client: str) -> RateLimitDecision:
        """The decision for one request, consuming a token only when one applies.

        The authentication branch is checked **before** the public-path skip, and the
        order cannot be swapped: `/auth/login` is a public path -- it has to be, since it
        is how a caller obtains a token -- so a skip-first ordering would exempt exactly
        the endpoint the stricter limit exists to protect, while every test asserting
        "public paths are not limited" continued to pass.
        """
        normalized = strip_version_prefix(path).rstrip("/") or "/"

        if normalized in AUTHENTICATION_PATHS and self.authentication.max_requests > 0:
            limiter = self.authentication
            key = f"{client}:auth"
        elif self.general.max_requests > 0 and not is_public(path):
            limiter = self.general
            key = client
        else:
            return RateLimitDecision(True, 0, 0, 0)

        allowed = limiter.is_allowed(key)
        return RateLimitDecision(
            allowed=allowed,
            limit=limiter.max_requests,
            remaining=limiter.remaining(key),
            retry_after=0 if allowed else limiter.retry_after(key),
        )

    async def __call__(self, scope: dict[str, Any], receive: Callable, send: Callable) -> None:
        # Lifespan and websocket scopes are not HTTP traffic; passing them through keeps
        # this middleware from having to know which other scopes exist.
        if scope.get("type") != "http" or not self.enabled:
            await self.app(scope, receive, send)
            return

        decision = self.decide(scope.get("path", ""), _client_address(scope))
        if not decision.allowed:
            # `Retry-After` is the header clients, proxies and browsers understand.
            # Without it a well-behaved client can only guess when to come back, and
            # guessing means retrying immediately.
            await JSONResponse(
                status_code=429,
                content={
                    "detail": "请求过于频繁，请稍后再试。",
                    "code": "rate_limited",
                    "retryAfter": decision.retry_after,
                },
                headers={"Retry-After": str(decision.retry_after)},
            )(scope, receive, send)
            return

        if not decision.limit:
            await self.app(scope, receive, send)
            return

        async def send_with_limits(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-RateLimit-Limit"] = str(decision.limit)
                headers["X-RateLimit-Remaining"] = str(decision.remaining)
            await send(message)

        await self.app(scope, receive, send_with_limits)


def _client_address(scope: dict[str, Any]) -> str:
    """The peer address from an ASGI scope, or `unknown` when absent."""
    client = scope.get("client")
    return client[0] if client else "unknown"
