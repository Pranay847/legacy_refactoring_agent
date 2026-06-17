"""
Supabase access layer (server-side, SERVICE ROLE).
====================================================================
This module is the single place the backend talks to Supabase/Postgres. It uses
the service-role key, which BYPASSES row-level security, so every function here
must be called only from trusted, already-authenticated server code.

Design notes:
  * Lazy imports — importing this module never fails just because the optional
    ``supabase`` package or env vars are missing. Errors surface only when a
    Supabase-backed feature is actually used.
  * Feature-gated — callers should check ``settings.supabase_enabled`` (or be
    prepared to catch RuntimeError) before relying on persistence.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

try:  # works whether launched from backend/ or as the backend package
    from config import settings
except ImportError:  # pragma: no cover
    from backend.config import settings


@lru_cache(maxsize=1)
def get_supabase_client():
    """Return a cached service-role Supabase client.

    Raises RuntimeError if Supabase is not configured or the client library is
    not installed, so callers fail loudly at the point of use.
    """
    if not settings.supabase_enabled:
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and "
            "SUPABASE_SERVICE_ROLE_KEY (see .env.example)."
        )
    try:
        from supabase import create_client
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "The 'supabase' package is not installed. Run "
            "`pip install -r requirements.txt`."
        ) from exc

    return create_client(
        settings.require("supabase_url"),
        settings.require("supabase_service_role_key"),
    )


def supabase_health() -> dict[str, Any]:
    """Lightweight connectivity probe for /api/status-style health checks.

    Never raises: returns a small status dict instead so it is safe to call from
    request handlers.
    """
    if not settings.supabase_enabled:
        return {"configured": False, "reachable": False}
    try:
        client = get_supabase_client()
        client.table("users").select("id").limit(1).execute()
        return {"configured": True, "reachable": True}
    except Exception as exc:  # noqa: BLE001 - health probe must not raise
        return {"configured": True, "reachable": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def get_or_create_user(clerk_user_id: str, email: str | None = None) -> str:
    """Return the public.users.id for a Clerk user, creating the row if needed."""
    client = get_supabase_client()
    found = (
        client.table("users")
        .select("id")
        .eq("clerk_user_id", clerk_user_id)
        .limit(1)
        .execute()
    )
    if found.data:
        return found.data[0]["id"]
    try:
        created = (
            client.table("users")
            .insert({"clerk_user_id": clerk_user_id, "email": email})
            .execute()
        )
        return created.data[0]["id"]
    except Exception:
        # Likely a concurrent insert hit the unique constraint; re-read.
        again = (
            client.table("users")
            .select("id")
            .eq("clerk_user_id", clerk_user_id)
            .limit(1)
            .execute()
        )
        if again.data:
            return again.data[0]["id"]
        raise


def find_user_id_by_customer(stripe_customer_id: str) -> str | None:
    """Reverse-lookup a user from their Stripe customer id (webhook path)."""
    client = get_supabase_client()
    res = (
        client.table("subscriptions")
        .select("user_id")
        .eq("stripe_customer_id", stripe_customer_id)
        .limit(1)
        .execute()
    )
    return res.data[0]["user_id"] if res.data else None


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------
def get_subscription(user_id: str) -> dict[str, Any] | None:
    client = get_supabase_client()
    res = (
        client.table("subscriptions")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def get_user_plan(user_id: str) -> str:
    """Return the active plan name ('free' if none/canceled)."""
    sub = get_subscription(user_id)
    if sub and sub.get("status") in {"active", "trialing", "past_due"}:
        return sub.get("plan") or "free"
    return "free"


def upsert_subscription(user_id: str, **fields: Any) -> None:
    client = get_supabase_client()
    payload = {"user_id": user_id, **{k: v for k, v in fields.items() if v is not None}}
    client.table("subscriptions").upsert(payload, on_conflict="user_id").execute()


# ---------------------------------------------------------------------------
# Usage events (plan-limit enforcement)
# ---------------------------------------------------------------------------
def count_usage_this_month(user_id: str, event_type: str) -> int:
    from datetime import datetime, timezone

    start = (
        datetime.now(timezone.utc)
        .replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        .isoformat()
    )
    client = get_supabase_client()
    res = (
        client.table("usage_events")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("event_type", event_type)
        .gte("created_at", start)
        .execute()
    )
    return res.count or 0


def insert_usage(
    user_id: str,
    event_type: str,
    project_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    client = get_supabase_client()
    client.table("usage_events").insert(
        {
            "user_id": user_id,
            "event_type": event_type,
            "project_id": project_id,
            "metadata": metadata or {},
        }
    ).execute()
