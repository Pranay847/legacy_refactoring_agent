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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="w-full max-w-lg rounded-[28px] border border-zinc-800 bg-zinc-950 shadow-2xl shadow-black/40">
        <div className="flex items-start justify-between gap-4 border-b border-zinc-800 px-6 py-5">
          <div className="flex items-start gap-4">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-500/12 text-emerald-300">
              <Icon size={20} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">{config.title}</h2>
              <p className="mt-1 text-sm text-zinc-400">{config.description}</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="rounded-full p-2 text-zinc-500 transition hover:bg-zinc-900 hover:text-zinc-200"
            aria-label="Close modal"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5 px-6 py-6">
          {mode === "github" ? (
            <label className="block">
              <span className="mb-2 flex items-center gap-2 text-sm font-medium text-zinc-200">
                <FolderGit2 size={16} />
                GitHub repo URL
              </span>
              <input
                autoFocus
                type="url"
                value={repoUrl}
                onChange={(event) => setRepoUrl(event.target.value)}
                placeholder="https://github.com/org/repo"
                className="w-full rounded-2xl border border-zinc-800 bg-zinc-900 px-4 py-3 text-sm text-zinc-100 outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-500/20"
              />
            </label>
          ) : null}

          <label className="block">
            <span className="mb-2 flex items-center gap-2 text-sm font-medium text-zinc-200">
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
              className="w-full rounded-2xl border border-zinc-800 bg-zinc-900 px-4 py-3 text-sm text-zinc-100 outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-500/20"
            />
            <p className="mt-2 text-xs text-zinc-500">
              This is added to the project header and can be renamed later.
            </p>
          </label>

          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-2xl border border-zinc-800 px-4 py-2.5 text-sm font-medium text-zinc-300 transition hover:bg-zinc-900"
            >
              Cancel
            </button>

            <button
              type="submit"
              className="rounded-2xl bg-emerald-500 px-4 py-2.5 text-sm font-medium text-zinc-950 transition hover:bg-emerald-400"
            >
              {config.submitLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
