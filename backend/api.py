"""
Compatibility shim.
====================================================================
The canonical FastAPI application now lives in ``app.py`` (referenced by the
``Procfile`` and ``api/index.py``). This module simply re-exports it so legacy
launch commands such as ``uvicorn api:app`` (from the ``backend/`` directory)
keep working.

Do NOT add endpoints or logic here. Edit ``app.py`` instead.
"""
try:
    # When launched from inside the backend/ directory (e.g. `uvicorn api:app`).
    from app import app
except ImportError:  # pragma: no cover
    # When imported as part of the `backend` package (e.g. `from backend.api import app`).
    from backend.app import app

__all__ = ["app"]
