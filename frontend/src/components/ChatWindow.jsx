import { useState } from "react";
import { SendHorizonal } from "lucide-react";
import { sendChatMessage } from "../api";

export default function ChatWindow({ session, addMessage, setSessionStatus }) {
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || !session) return;

    addMessage(session.id, { role: "user", content: trimmed });
    setInput("");
    setSending(true);
    setSessionStatus(session.id, "thinking");

    try {
      const data = await sendChatMessage(session.id, trimmed);

      addMessage(session.id, {
        role: "assistant",
        content: data.reply || "No response received.",
      });

      setSessionStatus(session.id, "ready");
    } catch (error) {
      console.error(error);
      addMessage(session.id, {
        role: "assistant",
        content: "There was an error processing your question.",
      });
      setSessionStatus(session.id, "error");
    } finally {
      setSending(false);
    }
  };

  if (!session) {
    return (
      <div className="flex h-full items-center justify-center rounded-2xl border border-zinc-200 bg-white dark:bg-zinc-900 p-6 shadow-sm">
        <p className="text-sm text-zinc-500">Create a session to start analyzing.</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col rounded-2xl border border-zinc-200 bg-white dark:bg-zinc-900 shadow-sm">
      <div className="flex-1 space-y-4 overflow-y-auto p-5">
        {session.messages.map((message) => (
          <div
            key={message.id}
            className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-6 ${
              message.role === "user"
                ? "ml-auto bg-blue-600 text-white"
                : "bg-zinc-100 dark:bg-zinc-600 text-zinc-800"
            }`}
          >
            {message.content}
          </div>
        ))}
      </div>

      <div className="border-t border-zinc-200 p-4">
        <div className="flex items-end gap-3">
          <textarea
            rows={3}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about the uploaded codebase, architecture, dependencies, or suggested service boundaries..."
            className="min-h-[84px] flex-1 resize-none rounded-2xl border border-zinc-300 px-4 py-3 text-sm text-zinc-900 dark:text-zinc-300 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />
          <button
            onClick={handleSend}
            disabled={sending}
            className="inline-flex h-12 items-center gap-2 rounded-2xl bg-zinc-900 px-5 font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <SendHorizonal size={16} />
            Send
          </button>
        </div>
      </div>
    </div>
  );
}