"""HTTP routers, grouped by concern.

`api.py` owns the app, the authentication middleware and the version mounting; the
routes themselves live here. The split is what makes each of those three reviewable:
in a single 2548-line module, the middleware that protects every endpoint sat 2300
lines away from the last endpoint it protects.

Routers import from `..http_runtime`, never from `..api`. Importing the app would be a
cycle, and the usual workaround -- a function-local import -- is the exact pattern
`test_module_boundaries.py` exists to prevent.

Stability: internal. The routes are the public surface; how they are grouped is not.
"""

from __future__ import annotations

from .auth_routes import router as auth_router
from .data_source_routes import router as data_source_router
from .knowledge_routes import router as knowledge_router
from .metamodel_routes import router as metamodel_router
from .model_governance_routes import router as model_governance_router
from .workflow_permission_routes import router as workflow_permission_router

__all__ = [
    "auth_router",
    "data_source_router",
    "knowledge_router",
    "metamodel_router",
    "model_governance_router",
    "workflow_permission_router",
]
