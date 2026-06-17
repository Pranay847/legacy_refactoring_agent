"""
Stripe subscription billing + usage limits (gated).
====================================================================
All Stripe calls are server-side. Subscription state is mirrored into the
``subscriptions`` table by signature-verified webhooks. Everything here is gated:

  * billing helpers raise RuntimeError when STRIPE_SECRET_KEY is missing;
  * ``meter()`` / ``enforce_and_record_usage()`` are NO-OPS unless auth + Supabase
    + Stripe are all configured, so local dev and partially-configured
    environments keep working.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, HTTPException, Request

try:  # works whether launched from backend/ or as the backend package
    from config import settings
    from auth import Principal, get_principal
except ImportError:  # pragma: no cover
    from backend.config import settings
    from backend.auth import Principal, get_principal


# Plan catalog. ``limits`` are per calendar month; None means unlimited.
PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "label": "Free",
        "limits": {"scan": 10, "cluster": 10, "generate": 20, "generate_all": 3, "chat": 50},
    },
    "pro": {
        "label": "Pro",
        "limits": {"scan": 200, "cluster": 200, "generate": 1000, "generate_all": 100, "chat": 2000},
    },
    "team": {
        "label": "Team",
        "limits": {"scan": None, "cluster": None, "generate": None, "generate_all": None, "chat": None},
    },
}


def _stripe():
    if not settings.billing_enabled:
        raise RuntimeError("Stripe billing is not configured (set STRIPE_SECRET_KEY).")
    try:
        import stripe
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("The 'stripe' package is not installed.") from exc
    stripe.api_key = settings.require("stripe_secret_key")
    return stripe


def price_for_plan(plan: str) -> Optional[str]:
    return {"pro": settings.stripe_price_pro, "team": settings.stripe_price_team}.get(plan)


def plan_for_price(price_id: str | None) -> str:
    if price_id and price_id == settings.stripe_price_team:
        return "team"
    if price_id and price_id == settings.stripe_price_pro:
        return "pro"
    return "free"


def _ts_to_iso(ts: int | None) -> str | None:
    if not ts:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Checkout / portal
# ---------------------------------------------------------------------------
def create_checkout_session(
    plan: str,
    clerk_user_id: str,
    email: str | None,
    success_url: str,
    cancel_url: str,
) -> str:
    stripe = _stripe()
    price = price_for_plan(plan)
    if not price:
        raise HTTPException(status_code=400, detail=f"Plan '{plan}' is not available for checkout.")
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=clerk_user_id,
        customer_email=email or None,
        allow_promotion_codes=True,
    )
    return session.url


def create_portal_session(customer_id: str, return_url: str) -> str:
    stripe = _stripe()
    session = stripe.billing_portal.Session.create(customer=customer_id, return_url=return_url)
    return session.url


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------
def construct_event(payload: bytes, sig_header: str):
    """Verify the Stripe signature and return the parsed event (raises on failure)."""
    stripe = _stripe()
    secret = settings.require("stripe_webhook_secret")
    try:
        return stripe.Webhook.construct_event(payload, sig_header, secret)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid Stripe signature: {exc}")


def _subscription_details(subscription_id: str | None) -> tuple[str, str, str | None]:
    """Return (plan, status, current_period_end_iso) for a Stripe subscription."""
    if not subscription_id:
        return ("free", "active", None)
    stripe = _stripe()
    sub = stripe.Subscription.retrieve(subscription_id)
    items = (sub.get("items") or {}).get("data") or []
    price_id = items[0]["price"]["id"] if items else None
    return (plan_for_price(price_id), sub.get("status", "active"), _ts_to_iso(sub.get("current_period_end")))


def handle_event(event: dict[str, Any]) -> None:
    """Apply a verified Stripe event to the subscriptions table (best-effort)."""
    if not settings.supabase_enabled:
        return
    from db import find_user_id_by_customer, get_or_create_user, upsert_subscription

    etype = event.get("type", "")
    obj = event.get("data", {}).get("object", {})

    if etype == "checkout.session.completed":
        clerk_user_id = obj.get("client_reference_id")
        if not clerk_user_id:
            return
        email = (obj.get("customer_details") or {}).get("email")
        user_id = get_or_create_user(clerk_user_id, email)
        plan, status, period_end = _subscription_details(obj.get("subscription"))
        upsert_subscription(
            user_id,
            stripe_customer_id=obj.get("customer"),
            stripe_subscription_id=obj.get("subscription"),
            plan=plan,
            status=status,
            current_period_end=period_end,
        )

    elif etype in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        customer_id = obj.get("customer")
        if not customer_id:
            return
        user_id = find_user_id_by_customer(customer_id)
        if not user_id:
            return
        items = (obj.get("items") or {}).get("data") or []
        price_id = items[0]["price"]["id"] if items else None
        plan = "free" if etype == "customer.subscription.deleted" else plan_for_price(price_id)
        upsert_subscription(
            user_id,
            stripe_customer_id=customer_id,
            stripe_subscription_id=obj.get("id"),
            plan=plan,
            status=obj.get("status", "active"),
            current_period_end=_ts_to_iso(obj.get("current_period_end")),
        )


# ---------------------------------------------------------------------------
# Usage metering (FastAPI dependency)
# ---------------------------------------------------------------------------
def _metering_active() -> bool:
    # Enforce limits only when we can identify the user (auth), persist usage
    # (Supabase) and know their plan (Stripe). Otherwise stay out of the way.
    return settings.auth_enabled and settings.supabase_enabled and settings.billing_enabled


def enforce_and_record_usage(principal: Principal, event_type: str) -> None:
    if not _metering_active():
        return
    from db import count_usage_this_month, get_or_create_user, get_user_plan, insert_usage

    user_id = get_or_create_user(principal.clerk_user_id, principal.email)
    plan = get_user_plan(user_id)
    limit = PLANS.get(plan, PLANS["free"])["limits"].get(event_type)
    if limit is not None:
        used = count_usage_this_month(user_id, event_type)
        if used >= limit:
            raise HTTPException(
                status_code=402,
                detail=(
                    f"Your {PLANS[plan]['label']} plan allows {limit} '{event_type}' "
                    f"actions per month and you've used {used}. Upgrade to continue."
                ),
            )
    insert_usage(user_id, event_type)


def meter(event_type: str):
    """Build a dependency that enforces + records one usage unit of ``event_type``."""

    def _dependency(request: Request):
        enforce_and_record_usage(get_principal(request), event_type)

    return Depends(_dependency)
