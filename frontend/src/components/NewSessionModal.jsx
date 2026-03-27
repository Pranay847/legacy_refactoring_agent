import { useEffect, useState } from "react";
import { X } from "lucide-react";

export default function NewSessionModal({ isOpen, onClose, onCreate }) {
  const [sessionName, setSessionName] = useState("");

  const handleClose = () => {
    setSessionName("");
    onClose();
  };

  useEffect(() => {
    const handleEscape = (event) => {
      if (event.key === "Escape") onClose();
    };

    if (isOpen) {
      window.addEventListener("keydown", handleEscape);
    }

    return () => window.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  const handleSubmit = (event) => {
    event.preventDefault();

    const trimmed = sessionName.trim();
    if (!trimmed) return;

    onCreate(trimmed);
    setSessionName("");
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
      <div className="w-full max-w-md rounded-3xl bg-white dark:bg-zinc-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-300">Create New Session</h2>
            <p className="mt-1 text-sm text-zinc-500">
              Give this workspace a name to start uploading and analyzing.
            </p>
          </div>

          <button
            onClick={handleClose}
            className="rounded-full p-2 text-zinc-500 transition hover:bg-zinc-100 dark:bg-zinc-600 hover:text-zinc-800"
            aria-label="Close modal"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-5">
          <label className="mb-2 block text-sm font-medium text-zinc-700">
            Project name
          </label>

          <input
            autoFocus
            type="text"
            value={sessionName}
            onChange={(e) => setSessionName(e.target.value)}
            placeholder="Example: Django Monolith Audit"
            className="w-full rounded-2xl border border-zinc-300 px-4 py-3 text-sm text-zinc-900 dark:text-zinc-300 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />

          <div className="mt-5 flex justify-end gap-3">
            <button
              type="button"
              onClick={handleClose}
              className="rounded-2xl border border-zinc-300 px-4 py-2.5 text-sm font-medium text-zinc-700 transition hover:bg-zinc-50 dark:bg-zinc-800"
            >
              Cancel
            </button>

            <button
              type="submit"
              className="rounded-2xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-blue-500"
            >
              Create Session
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
