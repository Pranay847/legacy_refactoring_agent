import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  UploadCloud,
  Network,
  Boxes,
  Cpu,
  ShieldCheck,
  History,
} from "lucide-react";
import { fetchStatus } from "../api";

const NAV_ITEMS = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "upload", label: "Upload Project", icon: UploadCloud },
  { id: "graph", label: "Graph View", icon: Network },
  { id: "clusters", label: "Clusters", icon: Boxes },
  { id: "microservices", label: "Microservices", icon: Cpu },
  { id: "validation", label: "Validation", icon: ShieldCheck },
  { id: "history", label: "History", icon: History },
];

export default function Sidebar({
  sessions,
  filteredSessions,
  activeSession,
  activeSessionId,
  onSelect,
  onCreateFromUpload,
  onCreateFromGithub,
  searchQuery,
  onSearchChange,
  onDeleteSession,
  onRepoPathChange,
  onScan,
  onCalculateMicroservices,
  onGenerateMicroservice,
  onGenerateAllMicroservices,
  onResetWorkspace,
  activeView,
  onViewChange,
}) {
  const [backendStatus, setBackendStatus] = useState({
    neo4j: "checking",
    anthropic: "checking",
  });

  // Check backend connectivity and integration readiness on mount.
  useEffect(() => {
    fetchStatus()
      .then((data) => {
        setBackendStatus({
          neo4j: data.neo4j_connected ? "connected" : "disconnected",
          anthropic: data.anthropic_configured ? "connected" : "disconnected",
        });
      })
      .catch(() => {
        setBackendStatus({ neo4j: "disconnected", anthropic: "disconnected" });
      });
  }, []);

  const handleNavClick = (itemId) => {
    // "Upload Monolith" is an action, not a view — open the file picker
    // and leave the current view highlighted.
    if (itemId === "upload") {
      onCreateFromUpload?.();
      return;
    }

    // Every other item navigates to a dashboard section (handled by the parent).
    onViewChange?.(itemId);
  };

  const currentView = activeView || "dashboard";

  return (
    <aside
      className="flex h-full flex-col overflow-hidden"
      style={{
        width: "var(--sidebar-width)",
        background: "var(--bg-sidebar)",
        borderRight: "1px solid var(--border-subtle)",
      }}
    >
      {/* Logo Section */}
      <div className="px-5 pt-6 pb-5">
        <div className="flex items-center gap-3">
          <div
            className="flex h-10 w-10 items-center justify-center rounded-xl"
            style={{
              background: "linear-gradient(135deg, #8b5cf6, #6366f1)",
              boxShadow: "0 0 16px rgba(139, 92, 246, 0.3)",
            }}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
              <path
                d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                stroke="white"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div>
            <h1
              className="text-base font-bold tracking-wide"
              style={{ color: "#f1f5f9" }}
            >
              M.A.C.E.
            </h1>
            <p
              className="text-[10px] leading-tight"
              style={{ color: "#64748b" }}
            >
              Monolith Analysis &
              <br />
              Clustering Engine
            </p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-2">
        <div className="space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = currentView === item.id;

            return (
              <button
                key={item.id}
                type="button"
                onClick={() => handleNavClick(item.id)}
                className={`nav-item ${isActive ? "active" : ""}`}
              >
                <Icon className="nav-icon" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      </nav>

      {/* Bottom Section: System Status */}
      <div
        className="mt-auto px-4 pb-5 pt-3"
        style={{ borderTop: "1px solid rgba(99, 102, 241, 0.12)" }}
      >
        {/* System Status */}
        <div>
          <p
            className="mb-2 text-[10px] font-semibold uppercase tracking-widest"
            style={{ color: "#64748b" }}
          >
            System Status
          </p>
          <p
            className="mb-2 text-xs font-medium"
            style={{
              color:
                backendStatus.neo4j === "connected"
                  ? "var(--accent-emerald)"
                  : backendStatus.neo4j === "checking"
                    ? "var(--accent-amber)"
                    : "var(--accent-rose)",
            }}
          >
            {backendStatus.neo4j === "connected" && backendStatus.anthropic === "connected"
              ? "All systems operational"
              : backendStatus.neo4j === "checking" || backendStatus.anthropic === "checking"
                ? "Checking connections..."
                : "Some services unavailable"}
          </p>
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span
                className={`status-dot ${backendStatus.neo4j === "connected" ? "connected" : "disconnected"}`}
              />
              <span className="text-[11px]" style={{ color: "#94a3b8" }}>
                Neo4j
              </span>
              <span className="ml-auto text-[10px]" style={{ color: "#64748b" }}>
                {backendStatus.neo4j === "connected"
                  ? "Connected"
                  : backendStatus.neo4j === "checking"
                    ? "Checking"
                    : "Offline"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`status-dot ${backendStatus.anthropic === "connected" ? "connected" : "disconnected"}`}
              />
              <span className="text-[11px]" style={{ color: "#94a3b8" }}>
                Anthropic
              </span>
              <span className="ml-auto text-[10px]" style={{ color: "#64748b" }}>
                {backendStatus.anthropic === "connected"
                  ? "Configured"
                  : backendStatus.anthropic === "checking"
                    ? "Checking"
                    : "Not configured"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
