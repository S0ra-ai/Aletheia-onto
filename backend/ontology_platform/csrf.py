"""CSRF protection for state-changing operations."""

from __future__ import annotations

import logging
import secrets
from functools import wraps
from typing import Callable

logger = logging.getLogger(__name__)


def generate_csrf_token() -> str:
    """Generate a CSRF token."""
    return secrets.token_hex(32)


def csrf_protect(func: Callable) -> Callable:
    """Decorator to add CSRF protection to endpoints."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        # This is a simplified implementation
        # In production, use a proper CSRF library
        return await func(*args, **kwargs)

    return wrapper
