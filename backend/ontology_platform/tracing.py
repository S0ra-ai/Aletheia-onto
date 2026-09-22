"""Distributed tracing support for request tracking.

Provides request ID generation and propagation across service boundaries.
Compatible with OpenTelemetry for production tracing.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Current request ID in context
_request_id: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Get the current request ID."""
    return _request_id.get()


def set_request_id(request_id: str | None = None) -> str:
    """Set or generate a request ID."""
    if request_id is None:
        request_id = str(uuid.uuid4())[:8]
    _request_id.set(request_id)
    return request_id


def clear_request_id() -> None:
    """Clear the current request ID."""
    _request_id.set("")


def tracing_middleware(func: Callable) -> Callable:
    """Decorator to add tracing to async functions."""

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Extract or generate request ID
        request_id = kwargs.get("request_id") or str(uuid.uuid4())[:8]
        _request_id.set(request_id)

        try:
            return await func(*args, **kwargs)
        finally:
            clear_request_id()

    return wrapper


def with_tracing(func: Callable) -> Callable:
    """Decorator to add tracing context to any function."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        request_id = get_request_id()
        logger.debug(f"[trace:{request_id}] Calling {func.__name__}")
        try:
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):

                async def await_result():
                    r = await result
                    logger.debug(f"[trace:{request_id}] {func.__name__} completed")
                    return r

                return await_result()
            logger.debug(f"[trace:{request_id}] {func.__name__} completed")
            return result
        except Exception as e:
            logger.error(f"[trace:{request_id}] {func.__name__} failed: {e}")
            raise

    return wrapper
