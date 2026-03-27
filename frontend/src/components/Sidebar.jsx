import { FolderKanban, MessageSquarePlus } from "lucide-react";

export default function Sidebar({ sessions, activeSessionId, onSelect, onCreate }) {
  return (
    <aside className="flex h-full w-80 flex-col border-r border-zinc-800 bg-zinc-950 text-zinc-100">
      <div className="border-b border-zinc-800 p-4">
        <button
          onClick={onCreate}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-3 font-medium text-white transition hover:bg-blue-500"
        >
          <MessageSquarePlus size={18} />
          New Project
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        <p className="mb-3 px-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">
          Previous Projects
        </p>

        <div className="space-y-2">
          {sessions.length === 0 ? (
            <div className="rounded-xl border border-dashed border-zinc-800 p-4 text-sm text-zinc-400">
              . . .
            </div>
          ) : (
            sessions.map((session) => {
              const isActive = session.id === activeSessionId;

              return (
                <button
                  key={session.id}
                  onClick={() => onSelect(session.id)}
                  className={`w-full rounded-2xl border p-3 text-left transition ${
                    isActive
                      ? "border-blue-500 bg-zinc-900"
                      : "border-zinc-800 bg-zinc-900/40 hover:bg-zinc-900"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <FolderKanban size={18} className="mt-0.5 text-zinc-400" />
                    <div className="min-w-0">
                      <p className="truncate font-medium text-zinc-100">{session.name}</p>
                      <p className="mt-1 text-xs text-zinc-400">
                        {session.files.length} files • {session.messages.length} messages
                      </p>
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>
    </aside>
  );
}