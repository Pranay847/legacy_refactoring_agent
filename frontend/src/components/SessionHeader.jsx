import { FileCode2, Sparkles } from "lucide-react";

export default function SessionHeader({ session }) {
  if (!session) {
    return (
      <div className="border-b border-zinc-200 bg-white dark:bg-zinc-900 p-6 dark:bg-zinc-900">
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-300">Code Refactoring</h1>
        <p className="mt-2 text-sm text-zinc-500">
          Create a session to begin uploading folders to analysis.
        </p>
      </div>
    );
  }

  return (
    <div className="border-b border-zinc-200 bg-white dark:bg-zinc-900 p-6 dark:bg-zinc-900">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-300">{session.name}</h1>
          <p className="mt-2 text-sm text-zinc-500">
            {session.files.length} files uploaded • Status: {session.status}
          </p>
        </div>

        <div className="flex gap-2">
          <div className="flex items-center gap-2 rounded-full border border-zinc-200 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-700">
            <FileCode2 size={16} />
            Code + Docs
          </div>
          <div className="flex items-center gap-2 rounded-full border border-zinc-200 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-700">
            <Sparkles size={16} />
            LLM Ready
          </div>
        </div>
      </div>
    </div>
  );
}