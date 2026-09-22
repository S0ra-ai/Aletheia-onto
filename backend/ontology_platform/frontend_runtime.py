"""Runtime helpers for serving the bundled admin application.

The API and the admin UI intentionally share one origin in the production image. That
keeps deployment to one container, while the Vite development server continues to proxy
``/api`` separately. This module only knows about the compiled frontend artifact; it does
not import the FastAPI app, so the API can still run from a wheel that does not include
the optional UI build.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

__all__ = ["frontend_assets", "frontend_index"]


def frontend_dist() -> Path:
    configured = os.environ.get("ALETHEIA_FRONTEND_DIST", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


def frontend_index() -> FileResponse | None:
    """Return the compiled SPA entry, or ``None`` for a kernel-only install."""
    index = frontend_dist() / "index.html"
    if not index.is_file():
        return None
    return FileResponse(index, media_type="text/html")


def frontend_assets() -> StaticFiles | None:
    """Build an assets mount only when the optional frontend artifact exists."""
    assets = frontend_dist() / "assets"
    if not assets.is_dir():
        return None
    return StaticFiles(directory=assets)
