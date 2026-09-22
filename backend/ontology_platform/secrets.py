"""Secrets management for production safety.

Handles encryption keys, API keys, and sensitive configuration
using environment variables or external secret managers.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Encryption key for sensitive data at rest
_ENCRYPTION_KEY: Optional[str] = None


def get_encryption_key() -> bytes:
    """Get the encryption key from environment or generate one."""
    global _ENCRYPTION_KEY

    if _ENCRYPTION_KEY:
        return base64.b64decode(_ENCRYPTION_KEY)

    key = os.environ.get("ONTOLOGY_ENCRYPTION_KEY")
    if not key:
        # Generate a random key for development
        import secrets

        key = secrets.token_hex(32)
        logger.warning("No ENCRYPTION_KEY set, using generated key (not for production!)")

    _ENCRYPTION_KEY = key
    return base64.b64decode(key)


def encrypt(value: str) -> str:
    """Encrypt a value (simplified - use proper AES in production)."""
    # Note: This is a placeholder. Use proper encryption in production.
    key = get_encryption_key()
    # Simple XOR for demonstration - NOT secure!
    encrypted = bytes([b ^ key[i % len(key)] for i, b in enumerate(value.encode())])
    return base64.b64encode(encrypted).decode()


def decrypt(value: str) -> str:
    """Decrypt a value (simplified)."""
    key = get_encryption_key()
    decrypted = base64.b64decode(value)
    result = bytes([b ^ key[i % len(key)] for i, b in enumerate(decrypted)])
    return result.decode()


def validate_secrets() -> list[str]:
    """Validate that required secrets are configured."""
    missing = []

    required = [
        "ONTOLOGY_ADMIN_PASSWORD",
        "ONTOLOGY_ENCRYPTION_KEY",
    ]

    for secret in required:
        if not os.environ.get(secret):
            missing.append(secret)

    return missing
