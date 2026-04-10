import { useEffect, useMemo, useRef, useState } from "react";
import {
  TimerReset,
  FileCode2,
  Folder,
  FolderGit2,
  FolderKanban,
  FolderTree,
  History,
  LoaderCircle,
  PanelLeftClose,
  Plus,
  RotateCcw,
  Search,
  Sparkles,
  Trash2,
  Workflow,
} from "lucide-react";

function formatTimestamp(timestamp) {
  if (!timestamp) return "No activity yet";

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

function getToolbarButtonClasses(isActive) {
  return `flex h-11 w-11 items-center justify-center rounded-2xl border transition duration-150 ${
    isActive
      ? "border-emerald-400 bg-emerald-500/18 text-zinc-100 shadow-[0_0_0_1px_rgba(52,211,153,0.12)]"
      : "border-zinc-800 bg-zinc-900 text-zinc-200 hover:-translate-y-0.5 hover:border-emerald-300 hover:bg-zinc-800 hover:text-white"
  }`;
}

function buildFileTree(files = []) {
  const root = [];

  files.forEach((file) => {
    const path = file.webkitRelativePath || file.name;
    const parts = path.split("/").filter(Boolean);

    let currentLevel = root;

    parts.forEach((part, index) => {
      const isLeaf = index === parts.length - 1;
      let existing = currentLevel.find((node) => node.name === part);

      if (!existing) {
        existing = {
          name: part,
          type: isLeaf ? "file" : "folder",
          children: [],
        };
        currentLevel.push(existing);
      }

      if (!isLeaf) {
        existing.type = "folder";
        currentLevel = existing.children;
      }
    });
  });

  const sortNodes = (nodes) =>
    nodes
      .sort((a, b) => {
        if (a.type !== b.type) {
          return a.type === "folder" ? -1 : 1;
        }

        return a.name.localeCompare(b.name);
      })
      .map((node) => ({
        ...node,
        children: sortNodes(node.children || []),
      }));

  return sortNodes(root);
}

function FileTreeNode({ node, depth = 0 }) {
  const isFolder = node.type === "folder";
  const Icon = isFolder ? Folder : FileCode2;

  return (
    <div>
      <div
        className="flex items-center gap-2 rounded-xl px-2 py-1.5 text-sm text-zinc-300"
        style={{ paddingLeft: `${depth * 14 + 8}px` }}
      >
        <Icon size={16} className={isFolder ? "text-emerald-300" : "text-zinc-500"} />
        <span className="truncate">{node.name}</span>
      </div>

      {isFolder
        ? node.children.map((child) => (
            <FileTreeNode key={`${node.name}-${child.name}`} node={child} depth={depth + 1} />
          ))
        : null}
    </div>
  );
}

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
  onToggleSidebar,
  onRepoPathChange,
  onScan,
  onCalculateMicroservices,
  onGenerateMicroservice,
  onResetWorkspace,
}) {
  const [isCreateMenuOpen, setIsCreateMenuOpen] = useState(false);
  const [isFilesOpen, setIsFilesOpen] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (!menuRef.current?.contains(event.target)) {
        setIsCreateMenuOpen(false);
      }
    };

    window.addEventListener("mousedown", handleClickOutside);
    return () => window.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const visibleSessions = isSearchOpen ? filteredSessions : sessions;
  const fileTree = useMemo(() => buildFileTree(activeSession?.files || []), [activeSession]);

  const handleCreateMenuToggle = () => {
    setIsCreateMenuOpen((value) => {
      const nextValue = !value;
      if (nextValue) {
        setIsFilesOpen(false);
        setIsSearchOpen(false);
        setIsHistoryOpen(false);
      }
      return nextValue;
    });
  };

  const handleFilesToggle = () => {
    setIsFilesOpen((value) => {
      const nextValue = !value;
      if (nextValue) {
        setIsCreateMenuOpen(false);
        setIsSearchOpen(false);
        setIsHistoryOpen(false);
      }
      return nextValue;
    });
  };

  const handleSearchToggle = () => {
    setIsSearchOpen((value) => {
      const nextValue = !value;
      if (nextValue) {
        setIsCreateMenuOpen(false);
        setIsFilesOpen(false);
        setIsHistoryOpen(false);
      }
      return nextValue;
    });
  };

  const handleHistoryToggle = () => {
    setIsHistoryOpen((value) => {
      const nextValue = !value;
      if (nextValue) {
        setIsCreateMenuOpen(false);
        setIsFilesOpen(false);
        setIsSearchOpen(false);
      }
      return nextValue;
    });
  };

  const panelTitle = isFilesOpen
    ? "Folder Tree"
    : isSearchOpen
      ? "Search Results"
      : isHistoryOpen
        ? "Chat History"
        : "Workspace";

  return (
    <aside className="relative z-20 flex h-full w-full flex-col overflow-visible bg-zinc-950 text-zinc-100">
      <div className="relative z-30 overflow-visible border-b border-zinc-800 px-3 py-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-zinc-500">
              Workspace
            </p>
            <h2 className="mt-2 text-lg font-semibold text-white">Projects</h2>
          </div>

          <button
            type="button"
            onClick={onToggleSidebar}
            className={getToolbarButtonClasses(false)}
            aria-label="Hide sidebar"
            title="Hide sidebar"
          >
            <PanelLeftClose size={18} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {activeSession ? (
          <div className="mb-4 rounded-3xl border border-zinc-800 bg-zinc-900/60 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-zinc-500">
                  Pipeline Controls
                </p>
                <h3 className="mt-2 text-sm font-semibold text-white">Demo Workflow</h3>
              </div>
              <div className="rounded-full border border-zinc-800 px-2.5 py-1 text-[11px] uppercase tracking-[0.2em] text-zinc-400">
                {activeSession.status}
              </div>
            </div>

            <label className="mt-4 block">
              <span className="mb-2 block text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
                Repository Path
              </span>
              <input
                type="text"
                value={activeSession.repoPath || ""}
                onChange={(event) => onRepoPathChange(activeSession.id, event.target.value)}
                placeholder="/Users/you/projects/legacy-monolith"
                className="w-full rounded-2xl border border-zinc-800 bg-zinc-950 px-4 py-3 text-sm text-zinc-100 outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-500/20"
              />
              <p className="mt-2 text-xs text-zinc-500">
                Use a local path the backend can read when running scan or generation.
              </p>
            </label>

            <div className="mt-4 space-y-2.5">
              <ActionButton
                icon={Search}
                title="Scan"
                description=""
                isLoading={activeSession.pipeline?.actionState?.scan === "running"}
                onClick={onScan}
              />
              <ActionButton
                icon={Workflow}
                title="Calculate Microservices"
                description=""
                isLoading={activeSession.pipeline?.actionState?.cluster === "running"}
                onClick={onCalculateMicroservices}
                disabled={!activeSession.pipeline?.scanSummary}
              />
              <ActionButton
                icon={Sparkles}
                title="Generate Microservice"
                description=""
                isLoading={activeSession.pipeline?.actionState?.generate === "running"}
                onClick={onGenerateMicroservice}
                disabled={!activeSession.pipeline?.selectedCluster}
              />
              <ActionButton
                icon={TimerReset}
                title="Reset Workspace"
                description=""
                isLoading={activeSession.pipeline?.actionState?.reset === "running"}
                onClick={onResetWorkspace}
                tone="muted"
              />
            </div>
          </div>
        ) : null}

        <div className="flex items-start gap-3">
          <div className="flex flex-col items-start gap-1.5">
            <div className="relative z-40" ref={menuRef}>
              <button
                type="button"
                onClick={handleCreateMenuToggle}
                className={getToolbarButtonClasses(isCreateMenuOpen)}
                aria-label="Create project"
                title="New project"
              >
                <Plus size={18} />
              </button>

              {isCreateMenuOpen ? (
                <div className="absolute left-[calc(100%+12px)] top-0 z-50 w-64 max-w-[calc(100vw-3rem)] rounded-2xl border border-zinc-800 bg-zinc-950 p-2 shadow-2xl shadow-black/40">
                  <button
                    type="button"
                    onClick={() => {
                      setIsCreateMenuOpen(false);
                      onCreateFromUpload();
                    }}
                    className="flex w-full items-start gap-3 rounded-xl px-3 py-3 text-left transition hover:bg-zinc-900"
                  >
                    <Folder size={18} className="mt-0.5 text-emerald-300" />
                    <span>
                      <span className="block text-sm font-medium text-white">Add file or folder</span>
                      <span className="mt-1 block text-xs text-zinc-400">
                        Start a new project session from local files.
                      </span>
                    </span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setIsCreateMenuOpen(false);
                      onCreateFromGithub();
                    }}
                    className="flex w-full items-start gap-3 rounded-xl px-3 py-3 text-left transition hover:bg-zinc-900"
                  >
                    <FolderGit2 size={18} className="mt-0.5 text-sky-300" />
                    <span>
                      <span className="block text-sm font-medium text-white">Add GitHub repo URL</span>
                      <span className="mt-1 block text-xs text-zinc-400">
                        Create a project session linked to a repository URL.
                      </span>
                    </span>
                  </button>
                </div>
              ) : null}
            </div>

            <button
              type="button"
              onClick={handleFilesToggle}
              className={getToolbarButtonClasses(isFilesOpen)}
              aria-label="Show folders"
              title="Folders"
            >
              <FolderTree size={18} />
            </button>

            <button
              type="button"
              onClick={handleSearchToggle}
              className={getToolbarButtonClasses(isSearchOpen)}
              aria-label="Search chat history"
              title="Search chat"
            >
              <Search size={18} />
            </button>

            <button
              type="button"
              onClick={handleHistoryToggle}
              className={getToolbarButtonClasses(isHistoryOpen)}
              aria-label="Toggle chat history"
              title="Chat history"
            >
              <History size={18} />
            </button>

          </div>

          <div className="min-w-0 flex-1">
            {isSearchOpen ? (
              <div className="mb-3">
                <label className="sr-only" htmlFor="chat-history-search">
                  Search chat history
                </label>
                <div className="flex items-center gap-3 rounded-2xl border border-zinc-800 bg-zinc-900 px-3 py-3">
                  <Search size={16} className="text-zinc-500" />
                  <input
                    id="chat-history-search"
                    type="text"
                    value={searchQuery}
                    onChange={(event) => onSearchChange(event.target.value)}
                    placeholder="Search all project conversations"
                    className="w-full border-0 bg-transparent text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
                  />
                </div>
              </div>
            ) : null}

            <p className="mb-3 px-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">
              {panelTitle}
            </p>

            {isFilesOpen ? (
              activeSession ? (
                activeSession.files.length > 0 ? (
                  <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 px-2 py-3">
                    {fileTree.map((node) => (
                      <FileTreeNode key={node.name} node={node} />
                    ))}
                  </div>
                ) : (
                  <div className="rounded-2xl border border-dashed border-zinc-800 px-4 py-5 text-sm text-zinc-500">
                    This project does not have uploaded files yet.
                  </div>
                )
              ) : (
                <div className="rounded-2xl border border-dashed border-zinc-800 px-4 py-5 text-sm text-zinc-500">
                  Select a project to inspect its files.
                </div>
              )
            ) : isHistoryOpen || isSearchOpen ? (
              <div className="space-y-2">
                {visibleSessions.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-zinc-800 px-4 py-5 text-sm text-zinc-500">
                    {isSearchOpen
                      ? "No chat matches found for that keyword."
                      : "No prior project sessions yet."}
                  </div>
                ) : (
                  visibleSessions.map((session) => {
                    const isActive = session.id === activeSessionId;
                    const latestMessage = session.messages[session.messages.length - 1];
                    const icon =
                      session.sourceType === "github" ? (
                        <FolderGit2 size={18} className="mt-0.5 text-sky-300" />
                      ) : (
                        <FolderKanban size={18} className="mt-0.5 text-emerald-300" />
                      );

                    return (
                      <div
                        key={session.id}
                        className={`rounded-2xl border p-3 transition ${
                          isActive
                            ? "border-emerald-400 bg-zinc-900"
                            : "border-zinc-800 bg-zinc-900/40 hover:bg-zinc-900"
                        }`}
                      >
                        <div className="flex items-start gap-3">
                          {icon}
                          <div className="min-w-0 flex-1">
                            <div className="flex items-start justify-between gap-3">
                              <button
                                type="button"
                                onClick={() => onSelect(session.id)}
                                className="min-w-0 flex-1 text-left"
                              >
                                <p className="truncate font-medium text-zinc-100">{session.name}</p>
                              </button>
                              <div className="flex items-center gap-2">
                                <span className="shrink-0 text-[11px] uppercase tracking-wide text-zinc-500">
                                  {session.sourceType === "github" ? "Repo" : "Files"}
                                </span>
                                <button
                                  type="button"
                                  onClick={() => {
                                    const confirmed = window.confirm(
                                      `Remove project "${session.name}" from saved sessions?`
                                    );
                                    if (confirmed) {
                                      onDeleteSession(session.id);
                                    }
                                  }}
                                  className="flex h-8 w-8 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 text-zinc-500 transition hover:border-rose-400 hover:bg-rose-500/10 hover:text-rose-200"
                                  aria-label={`Remove ${session.name}`}
                                  title="Remove project"
                                >
                                  <Trash2 size={15} />
                                </button>
                              </div>
                            </div>
                            <button
                              type="button"
                              onClick={() => onSelect(session.id)}
                              className="mt-1 block w-full text-left"
                            >
                              <p className="max-h-10 overflow-hidden text-xs text-zinc-400">
                                {latestMessage?.content ?? "No conversation yet."}
                              </p>
                              <p className="mt-3 text-[11px] text-zinc-500">
                                {formatTimestamp(session.updatedAt || session.createdAt)}
                              </p>
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed border-zinc-800 px-4 py-5 text-sm text-zinc-500">
                Choose a sidebar tool to create a project, inspect folders, search chats, or open history.
              </div>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}

function ActionButton({
  icon: Icon,
  title,
  description,
  isLoading = false,
  disabled = false,
  tone = "default",
  onClick,
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || isLoading}
      className={`flex w-full items-start gap-3 rounded-2xl border px-4 py-3 text-left transition ${
        tone === "muted"
          ? "border-zinc-800 bg-zinc-950 text-zinc-200 hover:bg-zinc-900"
          : "border-zinc-800 bg-zinc-950 text-zinc-100 hover:-translate-y-0.5 hover:border-emerald-400 hover:bg-zinc-900"
      } disabled:cursor-not-allowed disabled:opacity-50`}
    >
      <div className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-2xl bg-zinc-900">
        {isLoading ? (
          <LoaderCircle size={16} className="animate-spin text-emerald-300" />
        ) : (
          <Icon size={16} className={tone === "muted" ? "text-zinc-400" : "text-emerald-300"} />
        )}
      </div>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2 text-sm font-medium text-white">
          {title}
          {isLoading ? (
            <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-300">
              Running
            </span>
          ) : null}
        </span>
        <span className="mt-1 block text-xs leading-5 text-zinc-400">{description}</span>
      </span>
      <RotateCcw
        size={14}
        className={`mt-1 shrink-0 text-zinc-600 transition ${isLoading ? "opacity-0" : "opacity-100"}`}
      />
    </button>
  );
}
