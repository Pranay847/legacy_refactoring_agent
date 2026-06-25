import { useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  CheckCircle2,
  CircleDot,
  Clock,
  Code2,
  FileCode2,
  FileText,
  GitBranch,
  Info,
  Layers,
  LoaderCircle,
  Maximize2,
  Minimize2,
  RotateCcw,
  ScanSearch,
  Sparkles,
  Workflow,
  X,
  Zap,
} from "lucide-react";

/* ═══════════════════════════════════════════
   Utility helpers (unchanged logic)
   ═══════════════════════════════════════════ */

function formatNumber(value) {
  return new Intl.NumberFormat().format(value ?? 0);
}

function getClusterGraph(clusterSummary, graph) {
  const clusters = Object.entries(clusterSummary?.clusters || {});
  if (clusters.length === 0) return { nodes: [], edges: [] };

  const nodeByFunction = new Map();
  (graph?.nodes || []).forEach((node) => {
    nodeByFunction.set(node.data.id, node.data.cluster);
  });

  const edgeCounts = new Map();
  (graph?.edges || []).forEach((edge) => {
    const sourceCluster = nodeByFunction.get(edge.data.source);
    const targetCluster = nodeByFunction.get(edge.data.target);
    if (!sourceCluster || !targetCluster || sourceCluster === targetCluster) return;
    const key = [sourceCluster, targetCluster].sort().join("::");
    edgeCounts.set(key, (edgeCounts.get(key) || 0) + 1);
  });

  const radius = 120;
  const center = 160;
  const nodes = clusters.map(([name, data], index) => {
    const angle = (Math.PI * 2 * index) / clusters.length - Math.PI / 2;
    return {
      id: name,
      x: center + radius * Math.cos(angle),
      y: center + radius * Math.sin(angle),
      label: data.suggested_service,
      size: data.size,
    };
  });

  const positionedNodeMap = new Map(nodes.map((node) => [node.id, node]));
  const edges = Array.from(edgeCounts.entries()).map(([key, count]) => {
    const [source, target] = key.split("::");
    return {
      source: positionedNodeMap.get(source),
      target: positionedNodeMap.get(target),
      count,
    };
  });

  return { nodes, edges };
}

function getClusterMembers(graph, clusterName) {
  if (!clusterName) return [];
  return (graph?.nodes || [])
    .filter((node) => node.data.cluster === clusterName)
    .map((node) => ({
      id: node.data.id,
      label: node.data.label,
      module: node.data.module,
      line: node.data.lineno,
    }))
    .sort((a, b) => a.module.localeCompare(b.module) || a.line - b.line);
}

/** Internal-call ratio for a cluster (1.0 = fully cohesive). */
function clusterCohesion(clusterName, graph) {
  const members = new Set(
    (graph?.nodes || [])
      .filter((node) => node.data.cluster === clusterName)
      .map((node) => node.data.id)
  );
  if (members.size === 0) return null;

  let internal = 0;
  let external = 0;
  for (const edge of graph?.edges || []) {
    const srcIn = members.has(edge.data.source);
    const tgtIn = members.has(edge.data.target);
    if (srcIn && tgtIn) internal += 1;
    else if (srcIn || tgtIn) external += 1;
  }

  const total = internal + external;
  return total === 0 ? 1 : internal / total;
}

const CLUSTER_COLORS = [
  "#8b5cf6", "#06b6d4", "#f59e0b", "#ec4899",
  "#34d399", "#f97316", "#6366f1", "#14b8a6",
];

/* ═══════════════════════════════════════════
   Metric Cards Row
   ═══════════════════════════════════════════ */

function MetricCard({ label, value, change, changeDir, tone, icon: Icon }) {
  const toneClasses = {
    violet: "metric-violet",
    emerald: "metric-emerald",
    amber: "metric-amber",
    cyan: "metric-cyan",
    rose: "metric-rose",
  };

  const iconBgs = {
    violet: "rgba(139, 92, 246, 0.18)",
    emerald: "rgba(52, 211, 153, 0.18)",
    amber: "rgba(251, 191, 36, 0.18)",
    cyan: "rgba(34, 211, 238, 0.18)",
    rose: "rgba(251, 113, 133, 0.18)",
  };

  const iconColors = {
    violet: "#a78bfa",
    emerald: "#34d399",
    amber: "#fbbf24",
    cyan: "#22d3ee",
    rose: "#fb7185",
  };

  return (
    <div
      className={`glass-card-sm animate-fade-in ${toneClasses[tone] || ""}`}
      style={{ padding: "18px 20px" }}
    >
      <div className="flex items-start justify-between">
        <div>
          <p
            className="text-[11px] font-medium uppercase tracking-widest"
            style={{ color: "var(--text-muted)" }}
          >
            {label}
          </p>
          <p
            className="mt-2 text-2xl font-bold"
            style={{ color: "var(--text-primary)" }}
          >
            {value}
          </p>
          {change ? (
            <p
              className="mt-1 text-[11px] font-medium"
              style={{
                color: changeDir === "up" ? "var(--accent-emerald)" : "var(--accent-rose)",
              }}
            >
              {changeDir === "up" ? "▲" : "▼"} {change} vs last run
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          {Icon ? (
            <span
              className="flex h-9 w-9 items-center justify-center rounded-xl"
              style={{ background: iconBgs[tone], color: iconColors[tone] }}
            >
              <Icon size={18} />
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function MetricCardsRow({ session, verificationSummary }) {
  const pipeline = session?.pipeline || {};
  const scanSummary = pipeline.scanSummary;
  const clusterSummary = pipeline.clusterSummary;
  const generatedServices = pipeline.generatedServices;
  const generatedService = pipeline.generatedService;

  const functionsCount = scanSummary?.functions ?? 0;
  const clusterCount = clusterSummary?.clusterCount ?? 0;
  const microserviceCount =
    pipeline.backendServiceCount ??
    generatedServices?.length ??
    (generatedService ? 1 : 0);

  const totalVerification = verificationSummary?.total ?? 0;
  const passedVerification = verificationSummary?.passed ?? 0;
  const validationSuccess =
    totalVerification > 0
      ? `${Math.round((passedVerification / totalVerification) * 100)}%`
      : "—";

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-5">
      <MetricCard
        label="Functions Detected"
        value={formatNumber(functionsCount)}
        tone="violet"
        icon={GitBranch}
      />
      <MetricCard
        label="Clusters Found"
        value={formatNumber(clusterCount)}
        tone="amber"
        icon={BoxesIcon}
      />
      <MetricCard
        label="Microservices Generated"
        value={formatNumber(microserviceCount)}
        tone="emerald"
        icon={CpuIcon}
      />
      <MetricCard
        label="Validation Success"
        value={validationSuccess}
        tone="cyan"
        icon={CheckCircle2}
      />
      <MetricCard
        label="Last Run"
        value={session?.updatedAt ? timeAgo(session.updatedAt) : "—"}
        tone="rose"
        icon={Clock}
      />
    </div>
  );
}

function timeAgo(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins} min${mins > 1 ? "s" : ""} ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hr${hours > 1 ? "s" : ""} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days > 1 ? "s" : ""} ago`;
}

/* ═══════════════════════════════════════════
   Architecture Graph Widget
   ═══════════════════════════════════════════ */

function ArchitectureGraph({ id, session, onSelectCluster }) {
  const pipeline = session?.pipeline || {};
  const clusterSummary = pipeline.clusterSummary;
  const graph = pipeline.graph;
  const selectedCluster = pipeline.selectedCluster;
  const [isFullscreen, setIsFullscreen] = useState(false);
  const graphData = useMemo(
    () => getClusterGraph(clusterSummary, graph),
    [clusterSummary, graph]
  );

  const selectedClusterData = selectedCluster
    ? clusterSummary?.clusters?.[selectedCluster]
    : null;
  const members = getClusterMembers(graph, selectedCluster);

  useEffect(() => {
    if (!isFullscreen) return;
    const handleKey = (e) => { if (e.key === "Escape") setIsFullscreen(false); };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [isFullscreen]);

  const graphContent = (
    <div className="flex flex-1 gap-4">
      {/* Graph SVG */}
      <div
        className="flex-1 overflow-hidden rounded-xl"
        style={{ background: "rgba(10, 14, 26, 0.6)", border: "1px solid var(--border-subtle)" }}
      >
        {graphData.nodes.length === 0 ? (
          <div className="flex h-full min-h-[260px] items-center justify-center">
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              Run Calculate Microservices to reveal the architecture graph.
            </p>
          </div>
        ) : (
          <svg viewBox="0 0 320 320" className={isFullscreen ? "h-[500px] w-full" : "h-[280px] w-full"}>
            <defs>
              <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
                <path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgba(99,102,241,0.05)" strokeWidth="0.5" />
              </pattern>
            </defs>
            <rect width="320" height="320" fill="url(#grid)" />

            {graphData.edges.map((edge) => (
              <line
                key={`${edge.source.id}-${edge.target.id}`}
                x1={edge.source.x}
                y1={edge.source.y}
                x2={edge.target.x}
                y2={edge.target.y}
                stroke="rgba(139, 92, 246, 0.2)"
                strokeWidth={1 + Math.min(edge.count, 8) * 0.4}
                strokeDasharray={edge.count < 3 ? "4 4" : "none"}
              />
            ))}

            {graphData.nodes.map((node, idx) => {
              const isSelected = selectedCluster === node.id;
              const color = CLUSTER_COLORS[idx % CLUSTER_COLORS.length];

              return (
                <g
                  key={node.id}
                  onClick={() => onSelectCluster(session.id, node.id)}
                  className="cursor-pointer"
                >
                  {isSelected && (
                    <circle cx={node.x} cy={node.y} r={32} fill="none" stroke={color} strokeWidth="1" opacity="0.3" />
                  )}
                  <circle
                    cx={node.x} cy={node.y}
                    r={isSelected ? 26 : 22}
                    fill={isSelected ? color : "rgba(20, 25, 55, 0.9)"}
                    stroke={color} strokeWidth={isSelected ? 2.5 : 1.5}
                  />
                  <text x={node.x} y={node.y + 1} fill="#fff" fontSize="9" fontWeight="600" textAnchor="middle" dominantBaseline="middle">
                    {node.size}
                  </text>
                  <text x={node.x} y={node.y + 38} fill="rgba(148, 163, 184, 0.7)" fontSize="8" textAnchor="middle">
                    {node.label?.length > 12 ? node.label.slice(0, 12) + "…" : node.label}
                  </text>
                </g>
              );
            })}
          </svg>
        )}

        {graphData.nodes.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 px-4 pb-3">
            {graphData.nodes.map((node, idx) => (
              <div key={node.id} className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: CLUSTER_COLORS[idx % CLUSTER_COLORS.length] }} />
                <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                  {node.label || node.id}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Function Details Panel */}
      {selectedClusterData && (
        <div
          className="animate-slide-in-right w-[200px] shrink-0 overflow-y-auto rounded-xl"
          style={{ background: "var(--bg-card)", border: "1px solid var(--border-subtle)", padding: "16px" }}
        >
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs font-semibold" style={{ color: "var(--text-secondary)" }}>Function Details</p>
            <button onClick={() => onSelectCluster(session.id, null)} className="rounded p-0.5 transition hover:bg-white/5">
              <X size={12} style={{ color: "var(--text-muted)" }} />
            </button>
          </div>
          <div className="space-y-3">
            <div>
              <p className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>Function Name</p>
              <p className="mt-0.5 text-sm font-medium" style={{ color: "var(--text-primary)" }}>{members[0]?.label || "—"}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>Cluster</p>
              <span className="mt-0.5 inline-block rounded-md px-2 py-0.5 text-[11px] font-medium" style={{ background: "rgba(139, 92, 246, 0.15)", color: "#a78bfa" }}>
                {selectedCluster}
              </span>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>File</p>
              <p className="mt-0.5 text-xs" style={{ color: "var(--text-secondary)" }}>{members[0]?.module || "—"}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>Calls</p>
              <p className="mt-0.5 text-lg font-bold" style={{ color: "var(--text-primary)" }}>{members.length}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>Called By</p>
              <p className="mt-0.5 text-lg font-bold" style={{ color: "var(--text-primary)" }}>{selectedClusterData.size}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>Dependencies</p>
              <div className="mt-1 space-y-1">
                {members.slice(0, 5).map((m) => (
                  <p key={m.id} className="text-[11px]" style={{ color: "var(--accent-violet)" }}>• {m.label}</p>
                ))}
                {members.length > 5 && (
                  <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>+ {members.length - 5} more</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  if (isFullscreen) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col p-6" style={{ background: "rgba(10, 14, 26, 0.95)", backdropFilter: "blur(8px)" }}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Architecture Graph</h3>
          <button onClick={() => setIsFullscreen(false)} className="rounded-lg p-1.5 transition hover:bg-white/5">
            <X size={18} style={{ color: "var(--text-muted)" }} />
          </button>
        </div>
        <div className="flex-1">{graphContent}</div>
      </div>
    );
  }

  return (
    <div id={id} className="glass-card flex flex-col" style={{ padding: "20px", scrollMarginTop: "16px" }}>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Architecture Graph</h3>
          <Info size={13} style={{ color: "var(--text-muted)", cursor: "pointer" }} />
        </div>
        <button className="btn-secondary" style={{ fontSize: "11px", padding: "5px 12px" }} onClick={() => setIsFullscreen(true)}>
          View Fullscreen
        </button>
      </div>
      {graphContent}
    </div>
  );
}

/* ═══════════════════════════════════════════
   Surgery Room (Split Code Viewer)
   ═══════════════════════════════════════════ */

function SurgeryRoom({ id, session, onSelectCluster, onRegenerateMicroservice }) {
  const pipeline = session?.pipeline || {};
  const clusterSummary = pipeline.clusterSummary;
  const selectedCluster = pipeline.selectedCluster;
  const generatedService = pipeline.generatedService;
  const generatedServices = pipeline.generatedServices;
  const isGenerating = pipeline.actionState?.generate === "running";
  const isGeneratingAll = pipeline.actionState?.generateAll === "running";

  const repoPath =
    session?.repoPath ||
    session?.pipeline?.scanSummary?.repoPath ||
    "";

  const [activeServiceIndex, setActiveServiceIndex] = useState(0);
  const [activeFile, setActiveFile] = useState(null);
  const [displayCode, setDisplayCode] = useState("");
  const [isLoadingFile, setIsLoadingFile] = useState(false);
  const [fileCache, setFileCache] = useState({});
  const [originalCode, setOriginalCode] = useState("");
  const [isLoadingOriginal, setIsLoadingOriginal] = useState(false);

  const activeService = generatedServices?.length > 0
    ? generatedServices[activeServiceIndex] || generatedServices[0]
    : generatedService;

  const clusterNames = Object.keys(clusterSummary?.clusters || {});

  // The cluster whose code is currently on display — used to fetch the matching
  // original (pre-refactor) monolith source for the left pane.
  const activeClusterName =
    activeService?.cluster ||
    clusterNames.find((name) => activeService?.dir?.startsWith(`${name}_`)) ||
    selectedCluster ||
    null;

  useEffect(() => { setActiveServiceIndex(0); }, [generatedServices?.length]);

  // Keep the displayed service in sync with the cluster dropdown (batch mode).
  useEffect(() => {
    if (!selectedCluster || !(generatedServices?.length > 0)) return;
    const idx = generatedServices.findIndex(
      (svc) => svc.cluster === selectedCluster || svc.dir?.startsWith(`${selectedCluster}_`)
    );
    if (idx >= 0) setActiveServiceIndex(idx);
  }, [selectedCluster, generatedServices]);

  // Load the original monolith source for the active cluster so the left pane
  // shows the real pre-refactor code (not a copy of the generated service).
  useEffect(() => {
    if (!activeClusterName) {
      setOriginalCode("");
      return;
    }
    let cancelled = false;
    setIsLoadingOriginal(true);
    setOriginalCode("");
    import("../api").then(({ fetchClusterSource }) => {
      fetchClusterSource(activeClusterName, repoPath)
        .then((data) => {
          if (!cancelled) setOriginalCode(data.source || "");
        })
        .catch(() => {
          if (!cancelled) {
            setOriginalCode("# Could not load the original monolith source for this cluster.");
          }
        })
        .finally(() => {
          if (!cancelled) setIsLoadingOriginal(false);
        });
    });
    return () => { cancelled = true; };
  }, [activeClusterName, repoPath]);

  useEffect(() => {
    const defaultFile = activeService?.activeFile || null;
    setActiveFile(defaultFile);
    if (defaultFile && activeService?.code) {
      setFileCache({ [defaultFile]: activeService.code });
    } else {
      setFileCache({});
    }
  }, [activeService?.dir, activeService?.generationRevision]);

  useEffect(() => {
    if (!activeFile || !activeService?.dir) {
      setDisplayCode(activeService?.code || "");
      return;
    }
    if (fileCache[activeFile] !== undefined) {
      setDisplayCode(fileCache[activeFile]);
      return;
    }
    let cancelled = false;
    setIsLoadingFile(true);
    setDisplayCode("");
    import("../api").then(({ fetchServiceFile }) => {
      fetchServiceFile(activeService.dir, activeFile)
        .then((data) => {
          if (cancelled) return;
          const content = data.content || "";
          setFileCache((prev) => ({ ...prev, [activeFile]: content }));
          setDisplayCode(content);
        })
        .catch(() => {
          if (cancelled) return;
          setDisplayCode("// Failed to load file content");
        })
        .finally(() => {
          if (!cancelled) setIsLoadingFile(false);
        });
    });
    return () => { cancelled = true; };
  }, [activeFile, activeService?.dir]);

  const monolithCode = isLoadingOriginal
    ? "# Loading original source…"
    : originalCode || "# Select a cluster to view its original monolith code.";
  const microserviceCode = displayCode || "# Generated microservice code will appear here";

  return (
    <div id={id} className="glass-card flex flex-col" style={{ padding: "20px", scrollMarginTop: "16px" }}>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Surgery Room</h3>
          <Info size={13} style={{ color: "var(--text-muted)", cursor: "pointer" }} />
        </div>
        <div className="flex items-center gap-2">
          {clusterNames.length > 0 && (
            <select
              value={selectedCluster || ""}
              onChange={(e) => onSelectCluster(session.id, e.target.value || null)}
              className="rounded-lg px-3 py-1.5 text-xs font-medium outline-none"
              style={{ background: "var(--bg-card)", border: "1px solid var(--border-default)", color: "var(--text-primary)" }}
            >
              {clusterNames.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          )}
          <button
            className="btn-secondary"
            style={{ fontSize: "11px", padding: "5px 12px" }}
            disabled={isGenerating || isGeneratingAll || !selectedCluster}
            onClick={onRegenerateMicroservice}
          >
            <Sparkles size={13} />
            Regenerate
          </button>
        </div>
      </div>

      <div className="grid flex-1 gap-3 lg:grid-cols-2">
        {/* Original Monolith Code */}
        <div className="flex flex-col overflow-hidden rounded-xl" style={{ border: "1px solid var(--border-subtle)" }}>
          <div className="flex items-center justify-between px-4 py-2" style={{ background: "rgba(15, 19, 40, 0.8)", borderBottom: "1px solid var(--border-subtle)" }}>
            <p className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>Original Monolith Code</p>
            {isLoadingOriginal && (
              <div className="flex items-center gap-1.5">
                <LoaderCircle size={12} className="animate-spin" style={{ color: "var(--accent-cyan)" }} />
                <span className="text-[10px]" style={{ color: "var(--accent-cyan)" }}>Loading</span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-1 px-3 py-1.5" style={{ background: "rgba(10, 14, 26, 0.5)", borderBottom: "1px solid var(--border-subtle)" }}>
            <span className="file-tab active">
              <FileCode2 size={12} />
              {activeClusterName ? `${activeClusterName} (monolith)` : "monolith.py"}
            </span>
          </div>
          <pre className="code-editor flex-1 overflow-auto p-4" style={{ maxHeight: "300px", minHeight: "200px" }}>
            <code>{addLineNumbers(monolithCode)}</code>
          </pre>
        </div>

        {/* Generated Microservice */}
        <div className="flex flex-col overflow-hidden rounded-xl" style={{ border: "1px solid var(--border-subtle)" }}>
          <div className="flex items-center justify-between px-4 py-2" style={{ background: "rgba(15, 19, 40, 0.8)", borderBottom: "1px solid var(--border-subtle)" }}>
            <p className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>Generated Microservice</p>
            {(isGenerating || isLoadingFile) && (
              <div className="flex items-center gap-1.5">
                <LoaderCircle size={12} className="animate-spin" style={{ color: "var(--accent-violet)" }} />
                <span className="text-[10px]" style={{ color: "var(--accent-violet)" }}>{isLoadingFile ? "Loading" : "Generating"}</span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-1 px-3 py-1.5" style={{ background: "rgba(10, 14, 26, 0.5)", borderBottom: "1px solid var(--border-subtle)" }}>
            {activeService?.files ? (
              activeService.files.slice(0, 4).map((fileName) => (
                <button
                  key={fileName}
                  onClick={() => setActiveFile(fileName)}
                  className={`file-tab ${activeFile === fileName ? "active" : ""}`}
                >
                  <FileCode2 size={12} />
                  {fileName}
                </button>
              ))
            ) : (
              <span className="file-tab active"><FileCode2 size={12} />main.py</span>
            )}
          </div>
          <pre className="code-editor flex-1 overflow-auto p-4" style={{ maxHeight: "300px", minHeight: "200px" }}>
            <code>{addLineNumbers(microserviceCode)}</code>
          </pre>
        </div>
      </div>
    </div>
  );
}

function addLineNumbers(code) {
  if (!code) return "";
  const lines = code.split("\n");
  return lines.map((line, i) => `${String(i + 1).padStart(3, " ")}  ${line}`).join("\n");
}

/* ═══════════════════════════════════════════
   Clusters Overview Table
   ═══════════════════════════════════════════ */

function ClustersOverview({ id, session, onSelectCluster, onGenerateForCluster }) {
  const pipeline = session?.pipeline || {};
  const clusterSummary = pipeline.clusterSummary;
  const graph = pipeline.graph;
  const clusters = Object.entries(clusterSummary?.clusters || {});
  const isGenerating = pipeline.actionState?.generate === "running";

  return (
    <div id={id} className="glass-card" style={{ padding: "20px", scrollMarginTop: "16px" }}>
      <div className="mb-4 flex items-center gap-2">
        <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Clusters Overview</h3>
        <Info size={13} style={{ color: "var(--text-muted)", cursor: "pointer" }} />
      </div>

      {clusters.length === 0 ? (
        <p className="py-6 text-center text-xs" style={{ color: "var(--text-muted)" }}>
          Run Calculate Microservices to see clusters here.
        </p>
      ) : (
        <div className="overflow-auto" style={{ maxHeight: "260px" }}>
          <table className="dashboard-table">
            <thead>
              <tr>
                <th>Cluster</th>
                <th>Functions</th>
                <th>Cohesion Score</th>
                <th>Suggested Service</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {clusters.map(([name, data], idx) => (
                <tr key={name}>
                  <td>
                    <div className="flex items-center gap-2">
                      <span className="h-2.5 w-2.5 rounded-full" style={{ background: CLUSTER_COLORS[idx % CLUSTER_COLORS.length] }} />
                      <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>{name}</span>
                    </div>
                  </td>
                  <td>{data.size}</td>
                  <td>
                    {(() => {
                      const score = clusterCohesion(name, graph);
                      return score == null ? "—" : score.toFixed(2);
                    })()}
                  </td>
                  <td style={{ color: "var(--text-primary)" }}>{data.suggested_service}</td>
                  <td>
                    <button
                      className="btn-secondary"
                      style={{ fontSize: "10px", padding: "4px 10px" }}
                      disabled={isGenerating}
                      onClick={() => onGenerateForCluster(name)}
                    >
                      <Zap size={11} /> Generate
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════
   Recent Activity Feed
   ═══════════════════════════════════════════ */

function RecentActivity({ id, session }) {
  const messages = session?.messages || [];
  const recentMessages = messages.slice(-6).reverse();

  const getIcon = (content) => {
    if (content.includes("complet") || content.includes("success")) return CheckCircle2;
    if (content.includes("Generated") || content.includes("generat")) return Sparkles;
    if (content.includes("validat") || content.includes("pass")) return CheckCircle2;
    if (content.includes("Upload") || content.includes("upload")) return FileText;
    return CircleDot;
  };

  const getIconColor = (content) => {
    if (content.includes("fail") || content.includes("error")) return "var(--accent-rose)";
    if (content.includes("complet") || content.includes("success")) return "var(--accent-emerald)";
    if (content.includes("Generated") || content.includes("generat")) return "var(--accent-violet)";
    return "var(--accent-cyan)";
  };

  return (
    <div id={id} className="glass-card" style={{ padding: "20px", scrollMarginTop: "16px" }}>
      <div className="mb-4 flex items-center gap-2">
        <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Recent Activity</h3>
        <Info size={13} style={{ color: "var(--text-muted)", cursor: "pointer" }} />
      </div>

      {recentMessages.length === 0 ? (
        <p className="py-6 text-center text-xs" style={{ color: "var(--text-muted)" }}>
          No activity yet. Upload a Project to get started.
        </p>
      ) : (
        <div className="space-y-3" style={{ maxHeight: "240px", overflow: "auto" }}>
          {recentMessages.map((msg) => {
            const Icon = getIcon(msg.content);
            const iconColor = getIconColor(msg.content);
            return (
              <div key={msg.id} className="flex items-start gap-3 animate-fade-in">
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg" style={{ background: `${iconColor}15`, color: iconColor }}>
                  <Icon size={14} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                    {msg.content.length > 80 ? msg.content.slice(0, 80) + "…" : msg.content}
                  </p>
                  <p className="mt-0.5 text-[10px]" style={{ color: "var(--text-muted)" }}>
                    {msg.createdAt ? timeAgo(msg.createdAt) : "Just now"}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════
   Validation Results Widget
   ═══════════════════════════════════════════ */

function ValidationResults({ id, session, verification, isLoading }) {
  const summary = verification?.summary ?? { total: 0, passed: 0, failed: 0 };
  const results = verification?.results ?? [];
  const totalTests = summary.total ?? 0;
  const passed = summary.passed ?? 0;
  const failed = summary.failed ?? 0;
  const warnings = 0;
  const successRate = totalTests > 0 ? Math.round((passed / totalTests) * 100) : 0;
  const failedTests = results.filter((result) => result.passed === false);

  const size = 120;
  const strokeWidth = 8;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (successRate / 100) * circumference;
  const ringColor =
    totalTests === 0
      ? "var(--text-muted)"
      : failed > 0
        ? "var(--accent-amber)"
        : "var(--accent-emerald)";

  return (
    <div id={id} className="glass-card" style={{ padding: "20px", scrollMarginTop: "16px" }}>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Validation Results</h3>
          <Info size={13} style={{ color: "var(--text-muted)", cursor: "pointer" }} />
        </div>
        {isLoading && (
          <LoaderCircle size={14} className="animate-spin" style={{ color: "var(--accent-violet)" }} />
        )}
      </div>

      <div className="flex items-center gap-6">
        <div className="success-ring" style={{ width: size, height: size }}>
          <svg width={size} height={size}>
            <circle className="ring-bg" cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={strokeWidth} />
            <circle className="ring-fill" cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={strokeWidth} strokeDasharray={circumference} strokeDashoffset={offset} />
          </svg>
          <div className="ring-label">
            <span className="text-2xl font-bold" style={{ color: ringColor }}>
              {totalTests > 0 ? `${successRate}%` : "—"}
            </span>
            <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>Success Rate</span>
          </div>
        </div>

        <div className="flex-1 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>Total Tests</span>
            <span className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>{totalTests}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>Passed</span>
            <span className="text-sm font-semibold" style={{ color: "var(--accent-emerald)" }}>{passed}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>Failed</span>
            <span className="text-sm font-semibold" style={{ color: "var(--accent-rose)" }}>{failed}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>Warnings</span>
            <span className="text-sm font-semibold" style={{ color: "var(--accent-amber)" }}>{warnings}</span>
          </div>
        </div>
      </div>

      {totalTests === 0 && !isLoading && (
        <div className="mt-4 rounded-lg px-3 py-2" style={{ background: "rgba(148, 163, 184, 0.08)", border: "1px solid rgba(148, 163, 184, 0.15)" }}>
          <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
            No validation results yet. Shadow validation appears here after a configured test suite compares the original monolith with generated microservices.
          </p>
        </div>
      )}

      {failed > 0 && (
        <div className="mt-4 space-y-2">
          {failedTests.slice(0, 5).map((test) => (
            <div
              key={test.id || test.description}
              className="rounded-lg px-3 py-2"
              style={{ background: "rgba(251, 113, 133, 0.08)", border: "1px solid rgba(251, 113, 133, 0.15)" }}
            >
              <p className="text-[11px] font-medium" style={{ color: "var(--accent-rose)" }}>
                {test.description || test.id}
              </p>
              {(test.diff || []).slice(0, 2).map((line) => (
                <p key={line} className="mt-0.5 text-[10px]" style={{ color: "var(--text-muted)" }}>
                  {line}
                </p>
              ))}
            </div>
          ))}
        </div>
      )}

      {totalTests > 0 && failed === 0 && (
        <div className="mt-4 flex items-center gap-2 rounded-lg px-3 py-2" style={{ background: "rgba(52, 211, 153, 0.08)", border: "1px solid rgba(52, 211, 153, 0.15)" }}>
          <CheckCircle2 size={14} style={{ color: "var(--accent-emerald)" }} />
          <p className="text-[11px]" style={{ color: "var(--accent-emerald)" }}>
            All shadow tests passed. Generated microservices match monolith behavior.
          </p>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════
   Inline Icon Components
   ═══════════════════════════════════════════ */
function BoxesIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={props.size || 24} height={props.size || 24} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M2.97 12.92A2 2 0 0 0 2 14.63v3.24a2 2 0 0 0 .97 1.71l3 1.8a2 2 0 0 0 2.06 0L12 19v-5.5l-5-3-4.03 2.42Z" />
      <path d="m7 16.5-4.74-2.85" /><path d="m7 16.5 5-3" /><path d="M7 16.5v5.17" />
      <path d="M12 13.5V19l3.97 2.38a2 2 0 0 0 2.06 0l3-1.8a2 2 0 0 0 .97-1.71v-3.24a2 2 0 0 0-.97-1.71L17 10.5l-5 3Z" />
      <path d="m17 16.5-5-3" /><path d="m17 16.5 4.74-2.85" /><path d="M17 16.5v5.17" />
      <path d="M7.97 4.42A2 2 0 0 0 7 6.13v4.37l5 3 5-3V6.13a2 2 0 0 0-.97-1.71l-3-1.8a2 2 0 0 0-2.06 0l-3 1.8Z" />
      <path d="M12 8 7.26 5.15" /><path d="m12 8 4.74-2.85" /><path d="M12 13.5V8" />
    </svg>
  );
}

function CpuIcon(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={props.size || 24} height={props.size || 24} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <rect width="16" height="16" x="4" y="4" rx="2" /><rect width="6" height="6" x="9" y="9" rx="1" />
      <path d="M15 2v2" /><path d="M15 20v2" /><path d="M2 15h2" /><path d="M2 9h2" />
      <path d="M20 15h2" /><path d="M20 9h2" /><path d="M9 2v2" /><path d="M9 20v2" />
    </svg>
  );
}

/* ═══════════════════════════════════════════
   Pipeline Actions Toolbar
   ═══════════════════════════════════════════ */

function PipelineActions({
  session,
  onScan,
  onCalculateMicroservices,
  onGenerateMicroservice,
  onGenerateAllMicroservices,
  onResetWorkspace,
}) {
  const pipeline = session?.pipeline || {};
  const actionState = pipeline.actionState || {};

  const hasScan = (pipeline.scanSummary?.functions ?? 0) > 0;
  const clusterCount =
    pipeline.clusterSummary?.clusterCount ??
    Object.keys(pipeline.clusterSummary?.clusters || {}).length;
  const hasClusters = clusterCount > 0;
  const selectedCluster = pipeline.selectedCluster;

  const scanRunning = actionState.scan === "running";
  const clusterRunning = actionState.cluster === "running";
  const generateRunning = actionState.generate === "running";
  const generateAllRunning = actionState.generateAll === "running";
  const resetRunning = actionState.reset === "running";

  // "Scan" for a fresh project; "Re-scan" once the user has scanned it once.
  const scanLabel = pipeline.hasScanned ? "Re-scan" : "Scan";

  return (
    <div className="glass-card flex flex-wrap items-center gap-3" style={{ padding: "14px 18px" }}>
      <span
        className="text-[11px] font-semibold uppercase tracking-widest"
        style={{ color: "var(--text-muted)" }}
      >
        Pipeline
      </span>

      <button className="btn-secondary" onClick={onScan} disabled={scanRunning}>
        {scanRunning ? <LoaderCircle size={14} className="animate-spin" /> : <ScanSearch size={14} />}
        {scanRunning ? "Scanning…" : scanLabel}
      </button>

      <button
        className="btn-secondary"
        onClick={onCalculateMicroservices}
        disabled={clusterRunning || !hasScan}
        title={!hasScan ? "Upload or scan a codebase first" : undefined}
      >
        {clusterRunning ? <LoaderCircle size={14} className="animate-spin" /> : <Workflow size={14} />}
        {clusterRunning ? "Calculating…" : "Calculate Microservices"}
      </button>

      <button
        className="btn-secondary"
        onClick={onGenerateMicroservice}
        disabled={generateRunning || generateAllRunning || !hasClusters || !selectedCluster}
        title={
          !hasClusters
            ? "Calculate microservices first"
            : !selectedCluster
              ? "Select a cluster in the graph or clusters table"
              : `Generate code for ${selectedCluster}`
        }
      >
        {generateRunning ? <LoaderCircle size={14} className="animate-spin" /> : <Sparkles size={14} />}
        {generateRunning ? "Generating…" : "Generate Microservices"}
      </button>

      <button
        className="btn-secondary"
        onClick={onGenerateAllMicroservices}
        disabled={generateAllRunning || generateRunning || !hasClusters}
        title={!hasClusters ? "Calculate microservices first" : undefined}
      >
        {generateAllRunning ? <LoaderCircle size={14} className="animate-spin" /> : <Sparkles size={14} />}
        {generateAllRunning ? "Generating…" : "Generate All"}
      </button>

      <button
        type="button"
        className="ml-auto inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition hover:bg-white/5 disabled:opacity-50"
        style={{ border: "1px solid var(--border-default)", color: "var(--text-secondary)" }}
        onClick={onResetWorkspace}
        disabled={resetRunning}
      >
        <RotateCcw size={14} />
        {resetRunning ? "Resetting…" : "Reset Workspace"}
      </button>
    </div>
  );
}

/* ═══════════════════════════════════════════
   Main Export
   ═══════════════════════════════════════════ */

export default function ResultsPanel({
  session,
  activeView = "dashboard",
  onSelectCluster,
  onScan,
  onCalculateMicroservices,
  onGenerateMicroservice,
  onRegenerateMicroservice,
  onGenerateAllMicroservices,
  onGenerateForCluster,
  onResetWorkspace,
}) {
  const pipeline = session?.pipeline || {};
  const [verification, setVerification] = useState(null);
  const [verificationLoading, setVerificationLoading] = useState(false);

  useEffect(() => {
    if (!session) {
      setVerification(null);
      return undefined;
    }

    let cancelled = false;
    setVerificationLoading(true);
    import("../api")
      .then(({ fetchVerification }) => fetchVerification())
      .then((data) => {
        if (!cancelled) setVerification(data);
      })
      .catch(() => {
        if (!cancelled) setVerification(null);
      })
      .finally(() => {
        if (!cancelled) setVerificationLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    session?.id,
    session?.updatedAt,
    pipeline.actionState?.generate,
    pipeline.actionState?.generateAll,
    pipeline.actionState?.cluster,
    pipeline.actionState?.scan,
  ]);

  if (!session) {
    return (
      <div className="space-y-5 animate-fade-in">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-5">
          {["Functions Detected", "Clusters Found", "Microservices Generated", "Validation Success", "Last Run"].map(
            (label) => (
              <MetricCard key={label} label={label} value="—" tone="violet" />
            )
          )}
        </div>
        <div className="glass-card flex items-center justify-center" style={{ padding: "80px 20px" }}>
          <div className="text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl" style={{ background: "rgba(139, 92, 246, 0.1)" }}>
              <BarChart3 size={28} style={{ color: "var(--accent-violet)" }} />
            </div>
            <h3 className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>Welcome to M.A.C.E.</h3>
            <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>
              Upload a monolith codebase to begin analysis. The dashboard will populate
              <br />with architecture insights, cluster boundaries, and generated microservices.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const scanRunning = pipeline.actionState?.scan === "running";
  const clusterRunning = pipeline.actionState?.cluster === "running";
  const view = activeView || "dashboard";

  return (
    <div className="space-y-5 animate-fade-in">
      {scanRunning && (
        <div className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm" style={{ background: "rgba(139, 92, 246, 0.08)", border: "1px solid rgba(139, 92, 246, 0.2)", color: "var(--accent-violet)" }}>
          <LoaderCircle size={16} className="animate-spin" />
          Scanning repository and extracting function dependencies...
        </div>
      )}
      {clusterRunning && (
        <div className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm" style={{ background: "rgba(139, 92, 246, 0.08)", border: "1px solid rgba(139, 92, 246, 0.2)", color: "var(--accent-violet)" }}>
          <LoaderCircle size={16} className="animate-spin" />
          Calculating service boundaries and building the graph view...
        </div>
      )}

      {pipeline.error && (
        <div className="flex items-center justify-between rounded-xl px-4 py-3 text-sm" style={{ background: "rgba(251, 113, 133, 0.08)", border: "1px solid rgba(251, 113, 133, 0.2)", color: "var(--accent-rose)" }}>
          <span>{pipeline.error}</span>
          <button
            onClick={onResetWorkspace}
            className="ml-4 rounded-lg px-3 py-1 text-xs font-medium transition hover:bg-white/5"
            style={{ border: "1px solid rgba(251, 113, 133, 0.3)" }}
          >
            Dismiss & Reset
          </button>
        </div>
      )}

      {/* Pipeline action toolbar (available on every view) */}
      <PipelineActions
        session={session}
        onScan={onScan}
        onCalculateMicroservices={onCalculateMicroservices}
        onGenerateMicroservice={onGenerateMicroservice}
        onGenerateAllMicroservices={onGenerateAllMicroservices}
        onResetWorkspace={onResetWorkspace}
      />

      {view === "dashboard" && (
        <>
          <MetricCardsRow session={session} verificationSummary={verification?.summary} />
          <div className="grid gap-5 xl:grid-cols-[1fr_1.2fr]">
            <ArchitectureGraph session={session} onSelectCluster={onSelectCluster} />
            <SurgeryRoom session={session} onSelectCluster={onSelectCluster} onRegenerateMicroservice={onRegenerateMicroservice} />
          </div>
          <div className="grid gap-5 lg:grid-cols-3">
            <ClustersOverview session={session} onSelectCluster={onSelectCluster} onGenerateForCluster={onGenerateForCluster} />
            <RecentActivity session={session} />
            <ValidationResults session={session} verification={verification} isLoading={verificationLoading} />
          </div>
        </>
      )}

      {view === "graph" && (
        <ArchitectureGraph session={session} onSelectCluster={onSelectCluster} />
      )}

      {view === "clusters" && (
        <ClustersOverview session={session} onSelectCluster={onSelectCluster} onGenerateForCluster={onGenerateForCluster} />
      )}

      {view === "microservices" && (
        <SurgeryRoom session={session} onSelectCluster={onSelectCluster} onRegenerateMicroservice={onRegenerateMicroservice} />
      )}

      {view === "validation" && (
        <ValidationResults session={session} verification={verification} isLoading={verificationLoading} />
      )}

      {view === "history" && (
        <RecentActivity session={session} />
      )}
    </div>
  );
}
