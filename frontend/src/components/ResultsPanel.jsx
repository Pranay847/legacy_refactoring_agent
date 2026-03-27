import { BarChart3, FileText } from "lucide-react";

export default function ResultsPanel({ session }) {
  if (!session) {
    return (
      <div className="flex h-full items-center justify-center rounded-2xl border border-zinc-200 bg-white dark:bg-zinc-900 p-6 shadow-sm">
        <p className="text-sm text-zinc-500">Analysis results will appear here.</p>
      </div>
    );
  }

  return (
    <div className="h-full rounded-2xl border border-zinc-200 bg-white dark:bg-zinc-900 p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <BarChart3 size={18} className="text-zinc-700" />
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-300">Results</h2>
      </div>

      {session.results.length === 0 ? (
        <p className="text-sm text-zinc-500">
          No analysis results yet. Upload a folder to begin ingestion.
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
    </div>
  );
}