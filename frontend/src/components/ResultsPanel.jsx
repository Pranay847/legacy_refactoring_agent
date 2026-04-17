import { useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  CheckCircle2,
  CircleDot,
  FileCode2,
  FileText,
  Layers,
  LoaderCircle,
  Sparkles,
  Workflow,
} from "lucide-react";

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

function MetricCard({ label, value, tone = "default" }) {
  return (
    <div
      className={`rounded-2xl border px-4 py-4 ${
        tone === "accent"
          ? "border-emerald-300 bg-emerald-50 dark:border-emerald-700 dark:bg-emerald-950/40"
          : "border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-800/70"
      }`}
    >
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">{label}</p>
      <p className={`mt-2 font-semibold ${
        tone === "accent"
          ? "text-2xl text-emerald-800 dark:text-emerald-200"
          : "text-2xl text-zinc-900 dark:text-zinc-100"
      }`}>{value}</p>
    </div>
  );
}

function ClusterGraph({ clusterSummary, graph, selectedCluster, onSelectCluster }) {
  const graphData = useMemo(() => getClusterGraph(clusterSummary, graph), [clusterSummary, graph]);

  if (graphData.nodes.length === 0) {
    return (
      <div className="rounded-3xl border border-dashed border-zinc-300 bg-zinc-50 p-6 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900/60">
        Run microservice calculation to reveal the cluster graph.
      </div>
    );
  }

  return (
    <div className="rounded-3xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900/60">
      <div className="mb-4 flex items-center gap-2">
        <Workflow size={18} className="text-emerald-500" />
        <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-zinc-600 dark:text-zinc-300">
          Service Graph
        </h3>
      </div>

      <div className="overflow-hidden rounded-[24px] border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <svg viewBox="0 0 320 320" className="h-[320px] w-full">
          {graphData.edges.map((edge) => (
            <line
              key={`${edge.source.id}-${edge.target.id}`}
              x1={edge.source.x}
              y1={edge.source.y}
              x2={edge.target.x}
              y2={edge.target.y}
              stroke="rgba(113, 113, 122, 0.45)"
              strokeWidth={1 + Math.min(edge.count, 8) * 0.35}
            />
          ))}

          {graphData.nodes.map((node) => {
            const isSelected = selectedCluster === node.id;

            return (
              <g
                key={node.id}
                onClick={() => onSelectCluster(node.id)}
                className="cursor-pointer"
              >
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={isSelected ? 30 : 24}
                  fill={isSelected ? "#10b981" : "#18181b"}
                  stroke={isSelected ? "#a7f3d0" : "#3f3f46"}
                  strokeWidth="2"
                />
                <text
                  x={node.x}
                  y={node.y - 2}
                  fill="#fafafa"
                  fontSize="10"
                  textAnchor="middle"
                >
                  {node.id.replace("cluster_", "C")}
                </text>
                <text
                  x={node.x}
                  y={node.y + 12}
                  fill={isSelected ? "#022c22" : "#a1a1aa"}
                  fontSize="9"
                  textAnchor="middle"
                >
                  {node.size} fn
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {Object.entries(clusterSummary?.clusters || {}).map(([name, cluster]) => {
          const isSelected = selectedCluster === name;

          return (
            <button
              key={name}
              type="button"
              onClick={() => onSelectCluster(name)}
              className={`rounded-2xl border px-4 py-3 text-left transition ${
                isSelected
                  ? "border-emerald-300 bg-emerald-50 dark:bg-emerald-500/10"
                  : "border-zinc-200 bg-white hover:border-emerald-300 dark:border-zinc-800 dark:bg-zinc-950"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{name}</p>
                <span className="rounded-full bg-zinc-900 px-2 py-1 text-[11px] uppercase tracking-[0.18em] text-zinc-100">
                  {cluster.size} fn
                </span>
              </div>
              <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                {cluster.suggested_service}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ServiceCodeViewer({ service, isGenerating }) {
  const [activeFile, setActiveFile] = useState(service?.activeFile || null);
  const [displayCode, setDisplayCode] = useState("");
  const [isLoadingFile, setIsLoadingFile] = useState(false);
  // Cache: { [fileName]: content }
  const [fileCache, setFileCache] = useState({});

  // Reset when service changes
  useEffect(() => {
    const defaultFile = service?.activeFile || null;
    setActiveFile(defaultFile);
    // Seed cache with the pre-loaded code
    if (defaultFile && service?.code) {
      setFileCache({ [defaultFile]: service.code });
    } else {
      setFileCache({});
    }
  }, [service?.dir]);

  // Fetch file content when activeFile changes
  useEffect(() => {
    if (!activeFile || !service?.dir) {
      setDisplayCode(service?.code || "");
      return;
    }

    // Check cache first
    if (fileCache[activeFile] !== undefined) {
      setDisplayCode(fileCache[activeFile]);
      return;
    }

    // Fetch from backend
    let cancelled = false;
    setIsLoadingFile(true);
    setDisplayCode("");

    import("../api").then(({ fetchServiceFile }) => {
      fetchServiceFile(service.dir, activeFile)
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
  }, [activeFile, service?.dir]);

  return (
    <div className="rounded-[24px] border border-zinc-200 bg-zinc-950 p-4 text-zinc-100 dark:border-zinc-800">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <FileCode2 size={16} className="text-emerald-300" />
          <p className="text-sm font-semibold text-white">
            {activeFile || "main.py"}
          </p>
        </div>
        {isGenerating || isLoadingFile ? (
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-emerald-300">
            <LoaderCircle size={14} className="animate-spin" />
            {isLoadingFile ? "Loading" : "Generating"}
          </div>
        ) : displayCode ? (
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-emerald-300">
            <CheckCircle2 size={14} />
            Complete
          </div>
        ) : null}
      </div>

      {service?.files?.length > 1 ? (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {service.files.map((fileName) => (
            <button
              key={fileName}
              type="button"
              onClick={() => setActiveFile(fileName)}
              className={`rounded-lg px-2.5 py-1 text-xs transition ${
                activeFile === fileName
                  ? "bg-emerald-500/20 text-emerald-300"
                  : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
              }`}
            >
              {fileName}
            </button>
          ))}
        </div>
      ) : null}

      <pre className="min-h-[320px] max-h-[500px] overflow-auto rounded-2xl bg-black/30 p-4 text-xs leading-6 text-zinc-200">
        <code>
          {displayCode ||
            (isGenerating
              ? "# Waiting for generated code..."
              : isLoadingFile
                ? "# Loading file..."
                : "# Generated FastAPI service will appear here after you run Generate Microservice.")}
        </code>
      </pre>
    </div>
  );
}

function GenerationPreview({ session }) {
  const generatedService = session.pipeline?.generatedService;
  const generatedServices = session.pipeline?.generatedServices;
  const selectedCluster = session.pipeline?.selectedCluster;
  const isGenerating = session.pipeline?.actionState?.generate === "running";
  const isGeneratingAll = session.pipeline?.actionState?.generateAll === "running";
  const members = getClusterMembers(session.pipeline?.graph, selectedCluster);
  const [activeServiceIndex, setActiveServiceIndex] = useState(0);

  // Reset tab when services change
  useEffect(() => {
    setActiveServiceIndex(0);
  }, [generatedServices?.length]);

  // If we have batch-generated services, show the multi-service view
  if (generatedServices && generatedServices.length > 0) {
    const activeService = generatedServices[activeServiceIndex] || generatedServices[0];

    return (
      <div className="rounded-3xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900/60">
        <div className="mb-4 flex items-center gap-2">
          <Layers size={18} className="text-emerald-500" />
          <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-zinc-600 dark:text-zinc-300">
            Generated Services ({generatedServices.length})
          </h3>
          {isGeneratingAll ? (
            <div className="ml-auto flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-emerald-500">
              <LoaderCircle size={14} className="animate-spin" />
              Generating
            </div>
          ) : null}
        </div>

        {/* Service tabs */}
        <div className="mb-4 flex flex-wrap gap-2">
          {generatedServices.map((svc, index) => (
            <button
              key={svc.dir}
              type="button"
              onClick={() => setActiveServiceIndex(index)}
              className={`rounded-2xl border px-3 py-2 text-xs font-medium transition ${
                index === activeServiceIndex
                  ? "border-emerald-400 bg-emerald-500/10 text-emerald-300"
                  : "border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
              }`}
            >
              {svc.serviceName}
            </button>
          ))}
        </div>

        <ServiceCodeViewer service={activeService} isGenerating={false} />
      </div>
    );
  }

  // Fallback: single service or no services yet
  if (!selectedCluster && !generatedService) {
    return (
      <div className="rounded-3xl border border-dashed border-zinc-300 bg-zinc-50 p-6 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900/60">
        Select a cluster from the graph to prepare microservice generation.
      </div>
    );
  }

  return (
    <div className="rounded-3xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900/60">
      <div className="mb-4 flex items-center gap-2">
        <Sparkles size={18} className="text-emerald-500" />
        <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-zinc-600 dark:text-zinc-300">
          Generate Microservice
        </h3>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-[24px] border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
          <div className="mb-4 flex items-center gap-2">
            <CircleDot size={16} className="text-emerald-500" />
            <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              {selectedCluster || generatedService?.cluster || "Selected Cluster"}
            </p>
          </div>

          <div className="space-y-2">
            {members.length === 0 ? (
              <p className="text-sm text-zinc-500">
                Cluster members will appear here after graph data is available.
              </p>
            ) : (
              members.slice(0, 14).map((member) => (
                <div
                  key={member.id}
                  className="rounded-2xl border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900"
                >
                  <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                    {member.label}
                  </p>
                  <p className="mt-1 text-xs text-zinc-500">
                    {member.module}:{member.line}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>

        <ServiceCodeViewer service={generatedService} isGenerating={isGenerating} />
      </div>
    </div>
  );
}

export default function ResultsPanel({ session, onSelectCluster }) {
  if (!session) {
    return (
      <div className="flex h-full items-center justify-center rounded-2xl border border-zinc-200 bg-white dark:bg-zinc-900 p-6 shadow-sm">
        <p className="text-sm text-zinc-500">Analysis results will appear here.</p>
      </div>
    );
  }

  const pipeline = session.pipeline || {};
  const scanSummary = pipeline.scanSummary;
  const clusterSummary = pipeline.clusterSummary;
  const scanRunning = pipeline.actionState?.scan === "running";
  const clusterRunning = pipeline.actionState?.cluster === "running";

  return (
    <div className="h-full overflow-y-auto rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:bg-zinc-900">
      <div className="mb-4 flex items-center gap-2">
        <BarChart3 size={18} className="text-zinc-700" />
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-300">Results</h2>
      </div>

      {pipeline.error ? (
        <div className="mb-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {pipeline.error}
        </div>
      ) : null}

      {scanRunning ? (
        <div className="mb-4 flex items-center gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          <LoaderCircle size={16} className="animate-spin" />
          Scanning repository and extracting function dependencies...
        </div>
      ) : null}

      {clusterRunning ? (
        <div className="mb-4 flex items-center gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          <LoaderCircle size={16} className="animate-spin" />
          Calculating service boundaries and building the graph view...
        </div>
      ) : null}

      {scanSummary ? (
        <div className="mb-6 grid gap-3 md:grid-cols-3">
          <MetricCard label="Functions" value={formatNumber(scanSummary.functions)} tone="accent" />
          <MetricCard label="Dependencies" value={formatNumber(scanSummary.dependencies)} />
          <MetricCard label="Project" value={session.name || "Not set"} />
        </div>
      ) : session.results.length === 0 ? (
        <p className="text-sm text-zinc-500">
          No analysis results yet. Add a repository path in the sidebar and run Scan.
        </p>
      ) : (
        <div className="space-y-3">
          {session.results.map((result, index) => (
            <div key={index} className="rounded-2xl border border-zinc-200 bg-zinc-50 dark:bg-zinc-800 p-4">
              <div className="mb-2 flex items-center gap-2">
                <FileText size={16} className="text-zinc-600" />
                <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-300">
                  {result.file}
                </p>
              </div>
              <p className="text-sm text-zinc-600">
                Chunks created: <span className="font-medium">{result.chunks ?? 0}</span>
              </p>
              {result.summary && (
                <p className="mt-2 text-sm text-zinc-600">{result.summary}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {clusterSummary ? (
        <div className="space-y-6">
          <div className="rounded-3xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Cluster Summary
                </p>
                <h3 className="mt-2 text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                  {clusterSummary.clusterCount} distinct service clusters
                </h3>
              </div>
              <div className="rounded-full bg-emerald-100 px-3 py-1.5 text-sm font-semibold text-emerald-700">
                Louvain Ready
              </div>
            </div>
            <ClusterGraph
              clusterSummary={clusterSummary}
              graph={pipeline.graph}
              selectedCluster={pipeline.selectedCluster}
              onSelectCluster={(clusterName) => onSelectCluster(session.id, clusterName)}
            />
          </div>

          <GenerationPreview session={session} />
        </div>
      ) : null}
    </div>
  );
}
