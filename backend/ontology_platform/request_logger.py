"""Access logging middleware: one line per request, tied to its request id.

This is the log of record for "what did the API actually serve". It binds a request id
before anything else runs, so every log line any code emits during the request -- a
database warning, a rule-engine trace, an authorization denial -- carries the same id and
can be pulled out of the log with a single grep. Without the binding, correlating a
failure with the lines that explain it means matching timestamps, which fails exactly
when it matters: under concurrency.

Decisions that are visible in the output, and why:

**The path is logged, the query string is not.** Query strings routinely carry
credentials (`?token=...`, `?api_key=...`), and an access log is the one log that is
routinely shipped to a third-party aggregator. The path is the routing identity and is
enough to locate the handler; the parsed-and-validated parameters are already in the
request trace if someone needs them.

**The client address is the peer address, never `X-Forwarded-For`.** Behind a reverse
proxy that means every request logs as the proxy. That is less useful than the real
client, and deliberately so: the header is set by the caller, so reading it lets anyone
put a chosen address in an audit log. A coarse true address beats a precise unverified one.

**Duration is measured with a monotonic clock.** `time.time()` is wall-clock and is
adjusted by NTP; a correction mid-request produces a negative or absurd duration, and a
latency figure that is occasionally nonsense gets ignored entirely.

**Every request is logged, including health checks.** A probe that polls once a second
produces noise, but an access log that omits requests is not an access log -- it answers
"what was logged" instead of "what happened". Rates belong to `/metrics`.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from .tracing import REQUEST_ID_HEADER, bind_request_id, reset_request_id

logger = logging.getLogger(__name__)

# Response header carrying the id back to the caller, so a user can quote it in a bug
# report instead of quoting a timestamp.
REQUEST_ID_RESPONSE_HEADER = REQUEST_ID_HEADER


async def request_logging_middleware(request: Request, call_next: Callable) -> Response:
    """Bind a request id, serve the request, log one line, answer with the id.

    Registered as the outermost HTTP middleware so the id exists for every other
    middleware and endpoint, and so a request rejected during authentication is still
    logged with its id -- the denials are the lines an investigation wants most.
    """
    request_id, token = bind_request_id(request.headers.get(REQUEST_ID_HEADER))
    # Also on `request.state`, so handlers can include the id in a response body or an
    # error payload without importing the context.
    request.state.request_id = request_id

    started = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            # Logged with the id still bound, then re-raised: swallowing it here would
            # turn a 500 into whatever this middleware returned, and leave the traceback
            # unrecorded.
            logger.exception(
                "%s %s failed after %.2fms request_id=%s",
                request.method,
                request.url.path,
                _elapsed_ms(started),
                request_id,
            )
            raise

        duration_ms = _elapsed_ms(started)
        # 5xx is the server failing at something it promised; 4xx is the caller being told
        # no. Both are logged, at different levels, so an alert can key on the first
        # without paging on the second.
        level = logging.WARNING if response.status_code >= 500 else logging.INFO
        logger.log(
            level,
            "%s %s %d %.2fms client=%s request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            _client_address(request),
            request_id,
        )

        # Set here rather than in an endpoint: a caller needs the id even when the request
        # is rejected before any endpoint runs.
        response.headers[REQUEST_ID_RESPONSE_HEADER] = request_id
        return response
    finally:
        reset_request_id(token)


def _elapsed_ms(started: float) -> float:
    """Milliseconds since `started`, from a monotonic clock."""
    return (time.perf_counter() - started) * 1000


def _client_address(request: Request) -> str:
    """The peer address, or `unknown` when the transport does not report one."""
    client = request.client
    return client.host if client else "unknown"


async def unhandled_exception_response(request: Request, exc: Exception) -> Response:
    """A 500 the caller can actually report.

    Starlette's default is a plain `Internal Server Error` with no identifier, so a user
    reporting a crash has nothing to quote and support has to search by timestamp --
    which finds nothing when the timestamp is approximate, and everything when it is not.

    The exception message is deliberately *not* in the body. It carries filesystem paths,
    SQL fragments and occasionally row values, so echoing it turns an error report into a
    disclosure to whoever can reach the endpoint. The traceback goes to the log line,
    where it is readable by someone entitled to read it, keyed by the id in this body.

    Registered for `Exception`, which makes it the handler `ServerErrorMiddleware` calls.
    That middleware sits outside the application's own middleware stack, which is why the
    id cannot simply be attached here by the logging middleware: by the time this response
    is produced, no application middleware is running.
    """
    request_id = getattr(request.state, "request_id", "")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务内部错误，请携带 requestId 联系管理员。",
            "code": "internal_error",
            "requestId": request_id,
        },
        headers={REQUEST_ID_RESPONSE_HEADER: request_id} if request_id else None,
    )
