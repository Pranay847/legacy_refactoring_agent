import { useEffect, useRef, useState } from "react";
import Sidebar from "../components/Sidebar";
import SessionHeader from "../components/SessionHeader";
import ChatWindow from "../components/ChatWindow";
import ResultsPanel from "../components/ResultsPanel";
import NewSessionModal from "../components/NewSessionModal";
import useSessionStore from "../hooks/useSessionStore";

const SIDEBAR_WIDTH_KEY = "legacy-refactoring-sidebar-width";
const SIDEBAR_VISIBILITY_KEY = "legacy-refactoring-sidebar-visible";
const DEFAULT_SIDEBAR_WIDTH = 320;
const MIN_SIDEBAR_WIDTH = 260;
const MAX_SIDEBAR_WIDTH = 520;

function deriveProjectNameFromFiles(files) {
  const firstFile = files[0];
  if (!firstFile) return "Untitled Project";

  const relativePath = firstFile.webkitRelativePath || firstFile.name;
  const [topLevel] = relativePath.split("/");

  if (topLevel && topLevel !== firstFile.name) return topLevel;

  const fileName = firstFile.name.replace(/\.[^/.]+$/, "");
  return fileName || "Untitled Project";
}

export default function App() {
  const store = useSessionStore();
  const [modalState, setModalState] = useState({
    isOpen: false,
    mode: "upload",
    projectName: "",
    repoUrl: "",
  });
  const [searchQuery, setSearchQuery] = useState("");
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    if (typeof window === "undefined") return DEFAULT_SIDEBAR_WIDTH;

    const stored = Number(window.localStorage.getItem(SIDEBAR_WIDTH_KEY));
    if (Number.isNaN(stored) || stored <= 0) return DEFAULT_SIDEBAR_WIDTH;

    return Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, stored));
  });
  const [isSidebarVisible, setIsSidebarVisible] = useState(() => {
    if (typeof window === "undefined") return true;

    const stored = window.localStorage.getItem(SIDEBAR_VISIBILITY_KEY);
    return stored === null ? true : stored === "true";
  });
  const [isResizingSidebar, setIsResizingSidebar] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth));
  }, [sidebarWidth]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(SIDEBAR_VISIBILITY_KEY, String(isSidebarVisible));
  }, [isSidebarVisible]);

  useEffect(() => {
    if (!isResizingSidebar) return undefined;

    const handlePointerMove = (event) => {
      const nextWidth = Math.min(
        MAX_SIDEBAR_WIDTH,
        Math.max(MIN_SIDEBAR_WIDTH, event.clientX)
      );
      setSidebarWidth(nextWidth);
    };

    const handlePointerUp = () => {
      setIsResizingSidebar(false);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [isResizingSidebar]);

  const filteredSessions = store.sessions.filter((session) => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return true;

    const haystacks = [
      session.name,
      session.repoUrl,
      session.sourceLabel,
      ...session.messages.map((message) => message.content),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();

    return haystacks.includes(query);
  });

  const handleOpenUploadPicker = () => {
    fileInputRef.current?.click();
  };

  const handleFilesPicked = (event) => {
    const selectedFiles = Array.from(event.target.files || []);
    if (selectedFiles.length === 0) return;

    const defaultName = deriveProjectNameFromFiles(selectedFiles);
    const session = store.createSession({
      name: defaultName,
      sourceType: "upload",
      sourceLabel: "local file or folder",
      files: selectedFiles,
    });

    store.addMessage(session.id, {
      role: "assistant",
      content: `Added ${selectedFiles.length} local file${selectedFiles.length === 1 ? "" : "s"} to this project session.`,
    });

    event.target.value = "";
  };

  const handleOpenGithubModal = () => {
    setModalState({
      isOpen: true,
      mode: "github",
      projectName: "",
      repoUrl: "",
    });
  };

  const handleCloseModal = () => {
    setModalState((prev) => ({ ...prev, isOpen: false }));
  };

  const handleCreateGithubSession = ({ name, repoUrl }) => {
    const session = store.createSession({
      name,
      sourceType: "github",
      sourceLabel: "GitHub repo URL",
      repoUrl,
    });

    store.addMessage(session.id, {
      role: "assistant",
      content: `GitHub source saved for this project: ${repoUrl}`,
    });

    handleCloseModal();
  };

  const handleSearchChange = (value) => {
    setSearchQuery(value);
  };

  const handleToggleSidebar = () => {
    setIsSidebarVisible((value) => !value);
  };

  return (
    <div
      className={`relative h-screen bg-zinc-100 dark:bg-zinc-600 ${
        isResizingSidebar ? "select-none" : ""
      }`}
    >
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        onChange={handleFilesPicked}
        multiple
        webkitdirectory="true"
        directory=""
      />

      <div className="flex h-full">
        <div
          className={`relative shrink-0 overflow-visible transition-[width] duration-200 ease-out ${
            isSidebarVisible ? "border-r border-zinc-800" : "border-r-0"
          }`}
          style={{ width: isSidebarVisible ? sidebarWidth : 0 }}
        >
          {isSidebarVisible ? (
            <>
              <Sidebar
                sessions={store.sessions}
                filteredSessions={filteredSessions}
                activeSession={store.activeSession}
                activeSessionId={store.activeSessionId}
                onSelect={store.setActiveSessionId}
                onCreateFromUpload={handleOpenUploadPicker}
                onCreateFromGithub={handleOpenGithubModal}
                searchQuery={searchQuery}
                onSearchChange={handleSearchChange}
                onToggleSidebar={handleToggleSidebar}
              />

              <button
                type="button"
                onPointerDown={(event) => {
                  event.preventDefault();
                  setIsResizingSidebar(true);
                }}
                className="absolute right-0 top-0 h-full w-3 translate-x-1/2 cursor-col-resize bg-transparent"
                aria-label="Resize sidebar"
                title="Resize sidebar"
              >
                <span className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-zinc-700/80" />
              </button>
            </>
          ) : null}
        </div>

        <main className="flex min-w-0 flex-1 flex-col">
          <SessionHeader
            session={store.activeSession}
            isSidebarVisible={isSidebarVisible}
            onToggleSidebar={handleToggleSidebar}
          />

          <div className="grid min-h-0 flex-1 grid-cols-1 gap-6 p-6 xl:grid-cols-[1.4fr_1fr]">
            <div className="flex min-h-0 flex-col gap-6">
              <div className="min-h-0 flex-1">
                <ChatWindow
                  session={store.activeSession}
                  addMessage={store.addMessage}
                  setSessionStatus={store.setSessionStatus}
                />
              </div>
            </div>

            <div className="min-h-0">
              <ResultsPanel session={store.activeSession} />
            </div>
          </div>
        </main>
      </div>

      <NewSessionModal
        isOpen={modalState.isOpen}
        mode={modalState.mode}
        initialName={modalState.projectName}
        initialRepoUrl={modalState.repoUrl}
        onClose={handleCloseModal}
        onSubmit={handleCreateGithubSession}
      />
    </div>
  );
}
