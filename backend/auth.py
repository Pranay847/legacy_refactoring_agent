"""
Clerk authentication (gated).
====================================================================
Verifies Clerk-issued JWTs (RS256, validated against Clerk's JWKS). The whole
layer is gated on ``settings.auth_enabled`` (true only when CLERK_SECRET_KEY is
set):

  * auth DISABLED -> every request gets a synthetic dev principal and nothing is
    blocked, so local development works with no keys.
  * auth ENABLED  -> /api/* requests must carry a valid ``Authorization: Bearer``
    token (a few public paths are exempted, e.g. the Stripe webhook).

CORS must wrap this middleware so that 401 responses still carry CORS headers;
``install_auth(app)`` is therefore called *before* the CORS middleware in app.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

try:  # works whether launched from backend/ or as the backend package
    from config import settings
except ImportError:  # pragma: no cover
    from backend.config import settings


@dataclass
class Principal:
    """The authenticated caller for a request."""
    clerk_user_id: str
    email: Optional[str] = None
    claims: dict[str, Any] = field(default_factory=dict)
    is_dev: bool = False


# Used when auth is disabled so downstream code always has a user handle.
DEV_PRINCIPAL = Principal(clerk_user_id="local-dev", email=None, is_dev=True)

# /api paths that must work without a user token even when auth is enabled.
PUBLIC_API_PATHS = {
    "/api/status",          # health/integration flags (no per-user data yet)
    "/api/stripe/webhook",  # authenticated by Stripe signature, not a JWT
}


def _jwks_url() -> Optional[str]:
    if settings.clerk_jwks_url:
        return settings.clerk_jwks_url
    if settings.clerk_issuer:
        return settings.clerk_issuer.rstrip("/") + "/.well-known/jwks.json"
    return None


@lru_cache(maxsize=1)
def _jwk_client():
    url = _jwks_url()
    if not url:
        raise RuntimeError(
            "Clerk auth is enabled but neither CLERK_JWKS_URL nor CLERK_ISSUER is set."
        )
    from jwt import PyJWKClient  # lazy: only needed when auth is enabled
    return PyJWKClient(url)


def verify_bearer_token(token: str) -> Principal:
    """Verify a Clerk JWT and return a Principal, or raise HTTPException(401)."""
    try:
        import jwt  # PyJWT (lazy)
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=500,
            detail="PyJWT is not installed; run `pip install -r requirements.txt`.",
        ) from exc

    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
            issuer=settings.clerk_issuer or None,
            leeway=30,
        )
    except HTTPException:
        raise
    except Exception as exc:  # signature, expiry, network, etc.
        raise HTTPException(status_code=401, detail=f"Invalid authentication token: {exc}")

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token is missing the 'sub' claim.")
    return Principal(clerk_user_id=sub, email=claims.get("email"), claims=claims)


def _extract_bearer(request: Request) -> Optional[str]:
    header = request.headers.get("authorization")
    if not header:
        return None
    parts = header.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def install_auth(app) -> None:
    """Register the gated auth middleware on the FastAPI app."""

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        # Never block CORS preflight requests.
        if request.method == "OPTIONS":
            return await call_next(request)

        # Disabled -> attach dev principal, enforce nothing.
        if not settings.auth_enabled:
            request.state.principal = DEV_PRINCIPAL
            return await call_next(request)

        path = request.url.path
        if not path.startswith("/api"):
            return await call_next(request)

        # Public API paths: attach a principal if a token is present, but never require it.
        if path in PUBLIC_API_PATHS:
            token = _extract_bearer(request)
            request.state.principal = None
            if token:
                try:
                    request.state.principal = verify_bearer_token(token)
                except Exception:
                    request.state.principal = None
            return await call_next(request)

        token = _extract_bearer(request)
        if not token:
            return JSONResponse(status_code=401, content={"detail": "Missing bearer token."})
        try:
            request.state.principal = verify_bearer_token(token)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        except Exception as exc:  # pragma: no cover - defensive
            return JSONResponse(status_code=500, content={"detail": f"Auth error: {exc}"})
        return await call_next(request)


def get_principal(request: Request) -> Principal:
    """FastAPI dependency returning the current principal.

    Falls back to the dev principal when auth is disabled.
    """
    principal = getattr(request.state, "principal", None)
    if principal is not None:
        return principal
    if not settings.auth_enabled:
        return DEV_PRINCIPAL
    raise HTTPException(status_code=401, detail="Not authenticated.")
