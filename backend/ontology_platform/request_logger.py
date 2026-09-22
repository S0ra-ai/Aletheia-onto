"""Request logging middleware for audit trail.

Records all API requests with timestamps, IPs, and response times
for security auditing and troubleshooting.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from fastapi import Request, Response

logger = logging.getLogger(__name__)


async def request_logging_middleware(request: Request, call_next: Callable) -> Response:
    """Log all HTTP requests for audit purposes."""
    start_time = time.time()

    # Extract request info
    method = request.method
    path = request.url.path
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    # Process request
    response = await call_next(request)

    # Calculate duration
    duration_ms = (time.time() - start_time) * 1000

    # Log request
    logger.info(
        "%s %s %d %.2fms ip=%s agent=%s",
        method,
        path,
        response.status_code,
        duration_ms,
        client_ip,
        user_agent[:50],  # Truncate long user agents
    )

    # Add timing header
    response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"

    return response
