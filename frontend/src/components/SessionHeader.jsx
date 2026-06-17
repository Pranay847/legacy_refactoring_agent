import { UploadCloud } from "lucide-react";

export default function SessionHeader({
  session,
  onUploadClick,
}) {
  return (
    <header
      className="flex items-center justify-between gap-4 px-6 py-3"
      style={{
        background: "var(--bg-surface)",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      {/* Left: Project Selector */}
      <div className="flex items-center gap-5">
        <div>
          <p
            className="text-[11px] font-medium uppercase tracking-widest"
            style={{ color: "var(--text-muted)" }}
          >
            Project
          </p>
          <div
            className="mt-1 flex items-center gap-2 rounded-lg px-3 py-1.5"
            style={{
              border: "1px solid var(--border-default)",
              background: "var(--bg-card)",
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path
                d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                stroke="#8b5cf6"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
              {session?.name || "No Project Selected"}
            </span>
          </div>
        </div>
      </div>

      {/* Center: Page Title */}
      <div className="flex-1">
        <h1 className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>
          Dashboard
        </h1>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Overview of your monolith analysis
        </p>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onUploadClick}
          className="btn-primary"
        >
          <UploadCloud size={16} />
          Upload New Monolith
        </button>
      </div>
    </header>
  );
}
