import { useMemo, useState } from "react";

export default function useSessionStore() {
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) || null,
    [sessions, activeSessionId]
  );

  const createSession = (name) => {
    const newSession = {
      id: crypto.randomUUID(),
      name,
      files: [],
      messages: [
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `Session "${name}" created. Upload a folder and ask questions about the codebase.`,
        },
      ],
      results: [],
      createdAt: new Date().toISOString(),
      status: "idle",
    };

    setSessions((prev) => [newSession, ...prev]);
    setActiveSessionId(newSession.id);
  };

  const updateSession = (sessionId, updater) => {
    setSessions((prev) =>
      prev.map((session) =>
        session.id === sessionId
          ? typeof updater === "function"
            ? updater(session)
            : { ...session, ...updater }
          : session
      )
    );
  };

  const addMessage = (sessionId, message) => {
    updateSession(sessionId, (session) => ({
      ...session,
      messages: [
        ...session.messages,
        {
          id: crypto.randomUUID(),
          ...message,
        },
      ],
    }));
  };

  const setSessionFiles = (sessionId, files) => {
    updateSession(sessionId, { files });
  };

  const setSessionResults = (sessionId, results) => {
    updateSession(sessionId, { results });
  };

  const setSessionStatus = (sessionId, status) => {
    updateSession(sessionId, { status });
  };

  return {
    sessions,
    activeSession,
    activeSessionId,
    setActiveSessionId,
    createSession,
    updateSession,
    addMessage,
    setSessionFiles,
    setSessionResults,
    setSessionStatus,
  };
}