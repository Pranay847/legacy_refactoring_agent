import { useState } from "react";
import { SendHorizonal } from "lucide-react";
import { sendChatMessage } from "../api";
import ReactMarkdown from "react-markdown";

function MarkdownMessage({ content }) {
  return (
    <ReactMarkdown
      components={{
        h1: ({ children }) => (
          <h1 className="mb-2 mt-3 text-base font-bold text-zinc-900 dark:text-zinc-100">{children}</h1>
        ),
        h2: ({ children }) => (
          <h2 className="mb-2 mt-3 text-sm font-bold text-zinc-900 dark:text-zinc-100">{children}</h2>
        ),
        h3: ({ children }) => (
          <h3 className="mb-1 mt-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">{children}</h3>
        ),
        p: ({ children }) => (
          <p className="mb-2 last:mb-0">{children}</p>
        ),
        ul: ({ children }) => (
          <ul className="mb-2 ml-4 list-disc space-y-1">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="mb-2 ml-4 list-decimal space-y-1">{children}</ol>
        ),
        li: ({ children }) => (
          <li className="text-sm leading-6">{children}</li>
        ),
        strong: ({ children }) => (
          <strong className="font-semibold text-zinc-900 dark:text-zinc-100">{children}</strong>
        ),
        code: ({ inline, className, children }) => {
          if (inline) {
            return (
              <code className="rounded bg-zinc-200 px-1.5 py-0.5 text-xs font-mono text-emerald-700 dark:bg-zinc-700 dark:text-emerald-300">
                {children}
              </code>
            );
          }
          return (
            <pre className="my-2 overflow-auto rounded-xl bg-zinc-900 p-3 dark:bg-black/40">
              <code className="text-xs font-mono leading-5 text-zinc-200">
                {children}
              </code>
            </pre>
          );
        },
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-500 underline hover:text-blue-400">
            {children}
          </a>
        ),
        table: ({ children }) => (
          <div className="my-2 overflow-auto">
            <table className="w-full border-collapse text-xs">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="border-b border-zinc-300 dark:border-zinc-600">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="px-2 py-1.5 text-left font-semibold text-zinc-900 dark:text-zinc-100">{children}</th>
        ),
        td: ({ children }) => (
          <td className="border-t border-zinc-200 px-2 py-1.5 dark:border-zinc-700">{children}</td>
        ),
        hr: () => (
          <hr className="my-3 border-zinc-300 dark:border-zinc-600" />
        ),
        blockquote: ({ children }) => (
          <blockquote className="my-2 border-l-2 border-emerald-400 pl-3 text-zinc-600 dark:text-zinc-400">
            {children}
          </blockquote>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

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
                : "bg-zinc-100 dark:bg-zinc-600 text-zinc-800 dark:text-zinc-200"
            }`}
          >
            {message.role === "assistant" ? (
              <MarkdownMessage content={message.content} />
            ) : (
              message.content
            )}
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
