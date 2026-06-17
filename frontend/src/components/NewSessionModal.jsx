import { useEffect, useState } from "react";
import { FolderGit2, FolderPlus, PencilLine, X } from "lucide-react";

function deriveRepoName(repoUrl) {
  try {
    const url = new URL(repoUrl);
    const pathParts = url.pathname.split("/").filter(Boolean);
    const repoName = pathParts[pathParts.length - 1] || "";
    return repoName.replace(/\.git$/, "");
  } catch {
    return "";
  }
}

const SOURCE_COPY = {
  upload: {
    icon: FolderPlus,
    title: "Create Project From File Or Folder",
    description: "We will use the selected file or folder name as the default project name.",
    submitLabel: "Create Project",
  },
  github: {
    icon: FolderGit2,
    title: "Create Project From GitHub Repo",
    description: "Add a GitHub repository URL to open a new project session for that repo.",
    submitLabel: "Create Project",
  },
};

export default function NewSessionModal({
  isOpen,
  mode,
  initialName = "",
  initialRepoUrl = "",
  onClose,
  onSubmit,
}) {
  const [projectName, setProjectName] = useState(initialName);
  const [repoUrl, setRepoUrl] = useState(initialRepoUrl);
  const [lastDerivedName, setLastDerivedName] = useState("");

  useEffect(() => {
    setProjectName(initialName);
    setLastDerivedName(initialName);
  }, [initialName, isOpen]);

  useEffect(() => {
    setRepoUrl(initialRepoUrl);
  }, [initialRepoUrl, isOpen]);

  useEffect(() => {
    if (mode !== "github") return;

    const derivedName = deriveRepoName(repoUrl);
    if (!derivedName) return;

    if (!projectName || projectName === lastDerivedName) {
      setProjectName(derivedName);
      setLastDerivedName(derivedName);
    }
  }, [repoUrl, mode, projectName, lastDerivedName]);

  useEffect(() => {
    const handleEscape = (event) => {
      if (event.key === "Escape") onClose();
    };

    if (isOpen) {
      window.addEventListener("keydown", handleEscape);
    }

    return () => window.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const config = SOURCE_COPY[mode] ?? SOURCE_COPY.upload;
  const Icon = config.icon;

  const handleSubmit = (event) => {
    event.preventDefault();

    const trimmedName = projectName.trim();
    const trimmedRepoUrl = repoUrl.trim();

    if (!trimmedName) return;
    if (mode === "github" && !trimmedRepoUrl) return;

    onSubmit({
      name: trimmedName,
      repoUrl: trimmedRepoUrl,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4" style={{ background: "rgba(10, 14, 26, 0.8)", backdropFilter: "blur(8px)" }}>
      <div
        className="glass-card w-full max-w-lg animate-fade-in"
        style={{ border: "1px solid var(--border-default)" }}
      >
        <div
          className="flex items-start justify-between gap-4 px-6 py-5"
          style={{ borderBottom: "1px solid var(--border-subtle)" }}
        >
          <div className="flex items-start gap-4">
            <div
              className="flex h-11 w-11 items-center justify-center rounded-xl"
              style={{ background: "rgba(139, 92, 246, 0.12)", color: "#a78bfa" }}
            >
              <Icon size={20} />
            </div>
            <div>
              <h2 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
                {config.title}
              </h2>
              <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
                {config.description}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="rounded-full p-2 transition hover:bg-white/5"
            style={{ color: "var(--text-muted)" }}
            aria-label="Close modal"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5 px-6 py-6">
          {mode === "github" ? (
            <label className="block">
              <span className="mb-2 flex items-center gap-2 text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
                <FolderGit2 size={16} />
                GitHub repo URL
              </span>
              <input
                autoFocus
                type="url"
                value={repoUrl}
                onChange={(event) => setRepoUrl(event.target.value)}
                placeholder="https://github.com/org/repo"
                className="w-full rounded-xl px-4 py-3 text-sm outline-none transition"
                style={{
                  background: "var(--bg-card)",
                  border: "1px solid var(--border-default)",
                  color: "var(--text-primary)",
                }}
              />
            </label>
          ) : null}

          <label className="block">
            <span className="mb-2 flex items-center gap-2 text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
              <PencilLine size={16} />
              Project name
            </span>
            <input
              autoFocus={mode !== "github"}
              type="text"
              value={projectName}
              onChange={(event) => {
                setProjectName(event.target.value);
                setLastDerivedName("");
              }}
              placeholder="Example: Billing Service Rewrite"
              className="w-full rounded-xl px-4 py-3 text-sm outline-none transition"
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border-default)",
                color: "var(--text-primary)",
              }}
            />
            <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
              This is added to the project header and can be renamed later.
            </p>
          </label>

          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl px-4 py-2.5 text-sm font-medium transition hover:bg-white/5"
              style={{
                border: "1px solid var(--border-default)",
                color: "var(--text-secondary)",
              }}
            >
              Cancel
            </button>

            <button
              type="submit"
              className="btn-primary"
            >
              {config.submitLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
