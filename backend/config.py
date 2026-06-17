"""
Central configuration for the Legacy Refactoring Agent backend.
====================================================================
All environment-specific values and secrets are read here, once, from the
process environment plus an optional repo-root ``.env`` file. Nothing else in
the codebase should read ``os.environ`` for application config directly.

SECURITY: every secret in this module is SERVER-SIDE ONLY (Stripe secret key,
Supabase service-role key, Clerk secret key, etc.). Never import this module
into anything bundled for the browser. The frontend receives ONLY publishable /
anon keys, via its own ``VITE_*`` variables (see ``frontend/.env.example``).
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# .env loading (repo root)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _REPO_ROOT / ".env"


def _load_env_file(path: Path) -> None:
    """Populate os.environ from a .env file without overriding real env vars."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


_load_env_file(_ENV_PATH)


# ---------------------------------------------------------------------------
# Typed accessors
# ---------------------------------------------------------------------------
def _get(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if (value is not None and value != "") else default


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class Settings:
    """Process-wide configuration snapshot (read once at import time)."""

    # --- Runtime environment ---
    environment: str = _get("ENVIRONMENT", "development")
    debug: bool = _get_bool("DEBUG", environment != "production")

    # --- AI generation + graph database (existing) ---
    anthropic_api_key: str | None = _get("ANTHROPIC_API_KEY") or _get("API_KEY")
    neo4j_uri: str = _get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user: str = _get("NEO4J_USER", "neo4j")
    neo4j_password: str | None = _get("NEO4J_PASSWORD")
    generation_workers: int = _get_int("GENERATION_WORKERS", 5)
    generation_max_workers: int = _get_int("GENERATION_MAX_WORKERS", 10)

    # --- CORS / frontend ---
    frontend_url: str | None = _get("FRONTEND_URL")

    # --- Supabase (Phase 1) ---
    supabase_url: str | None = _get("SUPABASE_URL")
    supabase_anon_key: str | None = _get("SUPABASE_ANON_KEY")
    supabase_service_role_key: str | None = _get("SUPABASE_SERVICE_ROLE_KEY")

    # --- Clerk auth (Phase 2) ---
    clerk_publishable_key: str | None = _get("CLERK_PUBLISHABLE_KEY")
    clerk_secret_key: str | None = _get("CLERK_SECRET_KEY")
    clerk_jwks_url: str | None = _get("CLERK_JWKS_URL")
    clerk_issuer: str | None = _get("CLERK_ISSUER")

    # --- Stripe subscription tiers (Phase 3) ---
    stripe_secret_key: str | None = _get("STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = _get("STRIPE_WEBHOOK_SECRET")
    stripe_price_pro: str | None = _get("STRIPE_PRICE_PRO")
    stripe_price_team: str | None = _get("STRIPE_PRICE_TEAM")
    stripe_portal_return_url: str | None = _get("STRIPE_PORTAL_RETURN_URL")

    # --- Redis: caching + async job queue (Phases 4-5) ---
    redis_url: str | None = _get("REDIS_URL")

    # --- Derived feature flags: a feature turns on only when its keys exist ---
    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def auth_enabled(self) -> bool:
        return bool(self.clerk_secret_key)

    @property
    def billing_enabled(self) -> bool:
        return bool(self.stripe_secret_key)

    @property
    def redis_enabled(self) -> bool:
        return bool(self.redis_url)

    @property
    def rate_limit_enabled(self) -> bool:
        # Redis is the preferred backend; this flag forces the in-memory
        # fallback on for single-instance hosts without Redis.
        return _get_bool("RATE_LIMIT_ENABLED", False)

    @property
    def cors_origins(self) -> list[str]:
        # In production, do not trust localhost origins; only the configured
        # frontend URL (plus any explicit extras) may call the API.
        if self.environment == "production":
            origins: list[str] = []
        else:
            origins = [
                "http://localhost:5173",
                "http://localhost:5174",
                "http://localhost:3000",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:5174",
            ]
        if self.frontend_url and self.frontend_url not in origins:
            origins.append(self.frontend_url)
        return origins

    def require(self, attr: str) -> str:
        """Return a setting, raising a clear error if it is missing/empty.

        Use this at the point a feature is actually invoked so the app can boot
        without every integration configured.
        """
        value = getattr(self, attr, None)
        if not value:
            raise RuntimeError(
                f"Required configuration '{attr}' is not set. "
                f"Add the matching environment variable (see .env.example)."
            )
        return str(value)


settings = Settings()
