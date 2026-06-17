import { useState } from "react";
import { SendHorizonal } from "lucide-react";
import { sendChatMessage } from "../api";
import ReactMarkdown from "react-markdown";

function MarkdownMessage({ content }) {
  return (
    <ReactMarkdown
      components={{
        h1: ({ children }) => (
          <h1 className="mb-2 mt-3 text-base font-bold" style={{ color: "var(--text-primary)" }}>{children}</h1>
        ),
        h2: ({ children }) => (
          <h2 className="mb-2 mt-3 text-sm font-bold" style={{ color: "var(--text-primary)" }}>{children}</h2>
        ),
        h3: ({ children }) => (
          <h3 className="mb-1 mt-2 text-sm font-semibold" style={{ color: "var(--text-primary)" }}>{children}</h3>
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
          <strong className="font-semibold" style={{ color: "var(--text-primary)" }}>{children}</strong>
        ),
        code: ({ inline, className, children }) => {
          if (inline) {
            return (
              <code
                className="rounded px-1.5 py-0.5 text-xs font-mono"
                style={{ background: "rgba(139, 92, 246, 0.12)", color: "#a78bfa" }}
              >
                {children}
              </code>
            );
          }
          return (
            <pre className="code-editor my-2 overflow-auto p-3">
              <code className="text-xs font-mono leading-5" style={{ color: "var(--text-secondary)" }}>
                {children}
              </code>
            </pre>
          );
        },
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "var(--accent-violet)" }}
            className="underline hover:opacity-80"
          >
            {children}
          </a>
        ),
        table: ({ children }) => (
          <div className="my-2 overflow-auto">
            <table className="dashboard-table">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead style={{ borderBottom: "1px solid var(--border-subtle)" }}>{children}</thead>
        ),
        th: ({ children }) => (
          <th className="px-2 py-1.5 text-left font-semibold" style={{ color: "var(--text-primary)" }}>{children}</th>
        ),
        td: ({ children }) => (
          <td className="px-2 py-1.5" style={{ borderTop: "1px solid var(--border-subtle)" }}>{children}</td>
        ),
        hr: () => (
          <hr style={{ borderColor: "var(--border-subtle)" }} className="my-3" />
        ),
        blockquote: ({ children }) => (
          <blockquote className="my-2 border-l-2 pl-3" style={{ borderColor: "var(--accent-violet)", color: "var(--text-muted)" }}>
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
      <div
        className="glass-card flex h-full items-center justify-center"
        style={{ padding: "24px" }}
      >
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          Create a session to start analyzing.
        </p>
      </div>
    );
  }

  return (
    <div
      className="glass-card flex h-full flex-col"
      style={{ overflow: "hidden" }}
    >
      <div className="flex-1 space-y-4 overflow-y-auto p-5">
        {session.messages.map((message) => (
          <div
            key={message.id}
            className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-6 animate-fade-in ${
              message.role === "user" ? "ml-auto" : ""
            }`}
            style={
              message.role === "user"
                ? {
                    background: "linear-gradient(135deg, #8b5cf6, #6366f1)",
                    color: "#fff",
                  }
                : {
                    background: "var(--bg-card)",
                    border: "1px solid var(--border-subtle)",
                    color: "var(--text-secondary)",
                  }
            }
          >
            {message.role === "assistant" ? (
              <MarkdownMessage content={message.content} />
            ) : (
              message.content
            )}
          </div>
        ))}
      </div>

      <div
        className="p-4"
        style={{ borderTop: "1px solid var(--border-subtle)" }}
      >
        <div className="flex items-end gap-3">
          <textarea
            rows={3}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Ask about the uploaded codebase, architecture, dependencies, or suggested service boundaries..."
            className="min-h-[84px] flex-1 resize-none rounded-xl px-4 py-3 text-sm outline-none transition"
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border-default)",
              color: "var(--text-primary)",
            }}
          />
          <button
            onClick={handleSend}
            disabled={sending}
            className="btn-primary"
            style={{ height: "48px" }}
          >
            <SendHorizonal size={16} />
            Send
          </button>
        </div>
      </div>
    </div>
  );
}