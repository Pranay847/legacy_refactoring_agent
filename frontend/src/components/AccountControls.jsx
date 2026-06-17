import { useEffect, useState } from "react";
import { UserButton } from "@clerk/clerk-react";
import { Crown, Loader2, Settings2 } from "lucide-react";
import { fetchSubscription, startCheckout, openBillingPortal } from "../api";

// Rendered only when auth is enabled (so it always sits inside ClerkProvider).
export default function AccountControls() {
  const [sub, setSub] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    fetchSubscription()
      .then((data) => active && setSub(data))
      .catch(() => active && setSub(null));
    return () => {
      active = false;
    };
  }, []);

  const plan = sub?.plan || "free";
  const isPaid = plan === "pro" || plan === "team";

  const redirect = async (action) => {
    setBusy(true);
    setError(null);
    try {
      const { url } = await action();
      if (url) window.location.href = url;
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-3">
      <span
        className="rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest"
        style={{
          border: "1px solid var(--border-default)",
          background: "var(--bg-card)",
          color: isPaid ? "var(--accent-amber)" : "var(--text-muted)",
        }}
        title={error || (sub?.status ? `Status: ${sub.status}` : undefined)}
      >
        {plan}
      </span>

      {isPaid ? (
        <button
          type="button"
          onClick={() => redirect(openBillingPortal)}
          disabled={busy}
          className="btn-secondary"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Settings2 size={14} />}
          Manage
        </button>
      ) : (
        <button
          type="button"
          onClick={() => redirect(() => startCheckout("pro"))}
          disabled={busy}
          className="btn-secondary"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Crown size={14} />}
          Upgrade
        </button>
      )}

      <UserButton afterSignOutUrl="/" />
    </div>
  );
}
