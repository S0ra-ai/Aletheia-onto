"""What every route needs, and what `api.py` needs from every route.

`api.py` was one 2548-line module holding the app, the authentication middleware, 40
request models and 135 endpoints. Splitting it into routers requires somewhere for the
pieces they share to live, because the obvious arrangement does not work: a router that
imports `AUTH_ENABLED` from `api.py` while `api.py` imports the router is a cycle, and
the usual escape -- a function-local import -- is exactly the pattern
`test_module_boundaries.py` exists to prevent.

So the shared runtime moves *below* both. Routers import from here; `api.py` imports
from here and from the routers; nothing imports back.

What lives here is deliberately narrow: the authentication switch, the development
principal, and the dependency that reads the authenticated caller. These are the only
things a route needs that it cannot get from its own domain module.

`AUTH_ENABLED` in particular has to be read through this module rather than copied into
each router, because it is resolved once at import time. A copy per router would let one
of them disagree with the middleware about whether authentication is on -- and the
direction that disagreement fails is unauthenticated access.

Stability: internal. Routers are an implementation detail of the HTTP layer.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request

from .auth import Principal

__all__ = ["AUTH_ENABLED", "DEV_ADMIN_PRINCIPAL", "current_principal"]

# Authentication is on by default; it can only be disabled explicitly for local
# development, and the app logs loudly when it is. Only the documented opt-in values
# disable it: a typo must leave authentication on, because guessing at intent here
# would mean guessing in favour of exposure.
AUTH_ENABLED = os.environ.get("ONTOLOGY_AUTH_DISABLED", "").strip().lower() not in {"1", "true", "yes"}

DEV_ADMIN_PRINCIPAL = Principal(user_id=0, username="dev-anonymous", display_name="开发匿名用户", role_code="admin")


def current_principal(request: Request) -> Principal:
    """The authenticated caller, for handlers that need the acting identity.

    Read from request state, which the middleware populates -- never from the request
    body. An endpoint that accepted a caller-supplied actor would let anyone attribute
    their own writes to someone else, and the audit trail is the product here.
    """
    principal = getattr(request.state, "principal", None)
    if principal is None:
        if not AUTH_ENABLED:
            return DEV_ADMIN_PRINCIPAL
        raise HTTPException(status_code=401, detail="缺少访问令牌")
    return principal
