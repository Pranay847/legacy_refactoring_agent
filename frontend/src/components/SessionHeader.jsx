import { FileCode2, FolderGit2, PanelLeftOpen, Sparkles } from "lucide-react";

function SidebarToggleButton({ isSidebarVisible, onToggleSidebar }) {
  if (isSidebarVisible) return null;

  return (
    <button
      type="button"
      onClick={onToggleSidebar}
      className="flex h-11 w-11 items-center justify-center rounded-2xl border border-zinc-700 bg-zinc-950 text-zinc-100 shadow-sm transition duration-150 hover:-translate-y-0.5 hover:border-emerald-300 hover:bg-zinc-900 hover:text-white"
      aria-label="Show sidebar"
      title="Show sidebar"
    >
      <PanelLeftOpen size={18} />
    </button>
  );
}

export default function SessionHeader({ session, isSidebarVisible, onToggleSidebar }) {
  if (!session) {
    return (
      <div className="border-b border-zinc-200 bg-white p-6 dark:bg-zinc-900">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-start gap-4">
              <SidebarToggleButton
                isSidebarVisible={isSidebarVisible}
                onToggleSidebar={onToggleSidebar}
              />
              <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-300">
                Code Refactoring
              </h1>


            </div>

            <p className="mt-2 text-sm text-zinc-500">
              Start a new project from local files or a GitHub repository URL.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="border-b border-zinc-200 bg-white p-6 dark:bg-zinc-900">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-zinc-500">
                Active Project
              </p>
              <h1 className="mt-2 text-xl font-semibold text-zinc-900 dark:text-zinc-300">
                {session.name}
              </h1>
            </div>

            <SidebarToggleButton
              isSidebarVisible={isSidebarVisible}
              onToggleSidebar={onToggleSidebar}
            />
          </div>

          <p className="mt-2 text-sm text-zinc-500">
            {session.sourceType === "github" ? "GitHub repo session" : "Local file session"} •{" "}
            {session.files.length} files • Status: {session.status}
          </p>
          {session.repoUrl ? <p className="mt-2 text-sm text-zinc-500">{session.repoUrl}</p> : null}
        </div>

        <div className="flex gap-2">
          <div className="flex items-center gap-2 rounded-full border border-zinc-200 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-700">
            {session.sourceType === "github" ? <FolderGit2 size={16} /> : <FileCode2 size={16} />}
            {session.sourceType === "github" ? "GitHub Source" : "Code + Docs"}
          </div>
          <div className="flex items-center gap-2 rounded-full border border-zinc-200 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-700">
            <Sparkles size={16} />
            Project Header Synced
          </div>
        </div>
      </div>
    </div>
  );
}
