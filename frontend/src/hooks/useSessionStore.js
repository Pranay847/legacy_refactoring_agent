import { useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "legacy-refactoring-sessions";

const createInitialPipeline = () => ({
  scanSummary: null,
  clusterSummary: null,
  graph: null,
  selectedCluster: null,
  generatedService: null,
  actionState: {
    scan: "idle",
    cluster: "idle",
    generate: "idle",
    reset: "idle",
  },
  error: null,
});

const normalizeFiles = (files = []) =>
  files.map((file) => ({
    name: file.name,
    size: file.size ?? 0,
    type: file.type ?? "",
    webkitRelativePath: file.webkitRelativePath || file.name,
    lastModified: file.lastModified ?? null,
  }));

const createWelcomeMessage = (name, sourceLabel) => ({
  id: crypto.randomUUID(),
  role: "assistant",
  content: `Project "${name}" created from ${sourceLabel}. Start exploring the files or continue the conversation history here.`,
  createdAt: new Date().toISOString(),
});

export default function useSessionStore() {
  const [sessions, setSessions] = useState(() => {
    if (typeof window === "undefined") return [];

    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch (error) {
      console.error("Failed to restore sessions from localStorage", error);
      return [];
    }
  });
  const [activeSessionId, setActiveSessionId] = useState(() => {
    if (typeof window === "undefined") return null;

    try {
      const stored = window.localStorage.getItem(`${STORAGE_KEY}:active`);
      return stored || null;
    } catch (error) {
      console.error("Failed to restore active session from localStorage", error);
      return null;
    }
  });

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) || null,
    [sessions, activeSessionId]
  );

  useEffect(() => {
    if (typeof window === "undefined") return;

    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  }, [sessions]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    if (activeSessionId) {
      window.localStorage.setItem(`${STORAGE_KEY}:active`, activeSessionId);
      return;
    }

    window.localStorage.removeItem(`${STORAGE_KEY}:active`);
  }, [activeSessionId]);

  useEffect(() => {
    if (activeSessionId && !sessions.some((session) => session.id === activeSessionId)) {
      setActiveSessionId(sessions[0]?.id ?? null);
    }
  }, [activeSessionId, sessions]);

  const createSession = ({
    name,
    sourceType = "upload",
    sourceLabel = "local files",
    repoUrl = "",
    files = [],
  }) => {
    const newSession = {
      id: crypto.randomUUID(),
      name,
      files: normalizeFiles(files),
      messages: [createWelcomeMessage(name, sourceLabel)],
      results: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      status: "idle",
      sourceType,
      sourceLabel,
      repoUrl,
      repoPath: "",
      pipeline: createInitialPipeline(),
    };

    setSessions((prev) => [newSession, ...prev]);
    setActiveSessionId(newSession.id);

    return newSession;
  };

  const updateSession = (sessionId, updater) => {
    setSessions((prev) =>
      prev.map((session) =>
        session.id === sessionId
          ? typeof updater === "function"
            ? { ...updater(session), updatedAt: new Date().toISOString() }
            : { ...session, ...updater, updatedAt: new Date().toISOString() }
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
          createdAt: message.createdAt ?? new Date().toISOString(),
        },
      ],
    }));
  };

  const renameSession = (sessionId, name) => {
    updateSession(sessionId, { name });
  };

  const setSessionFiles = (sessionId, files) => {
    updateSession(sessionId, { files: normalizeFiles(files) });
  };

  const setSessionResults = (sessionId, results) => {
    updateSession(sessionId, { results });
  };

  const setSessionStatus = (sessionId, status) => {
    updateSession(sessionId, { status });
  };

  const setSessionRepoPath = (sessionId, repoPath) => {
    updateSession(sessionId, { repoPath });
  };

  const resetSessionPipeline = (sessionId) => {
    updateSession(sessionId, { pipeline: createInitialPipeline() });
  };

  const clearAllSessions = () => {
    setSessions([]);
    setActiveSessionId(null);
  };

  const deleteSession = (sessionId) => {
    setSessions((prev) => {
      const nextSessions = prev.filter((session) => session.id !== sessionId);
      setActiveSessionId((prevActiveId) =>
        prevActiveId === sessionId ? nextSessions[0]?.id ?? null : prevActiveId
      );
      return nextSessions;
    });
  };

  return {
    sessions,
    activeSession,
    activeSessionId,
    setActiveSessionId,
    createSession,
    updateSession,
    addMessage,
    renameSession,
    setSessionFiles,
    setSessionResults,
    setSessionStatus,
    setSessionRepoPath,
    resetSessionPipeline,
    deleteSession,
    clearAllSessions,
  };
}
