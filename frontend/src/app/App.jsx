import { useEffect, useRef, useState } from "react";
import Sidebar from "../components/Sidebar";
import SessionHeader from "../components/SessionHeader";
import ChatWindow from "../components/ChatWindow";
import ResultsPanel from "../components/ResultsPanel";
import NewSessionModal from "../components/NewSessionModal";
import useSessionStore from "../hooks/useSessionStore";
import {
  calculateMicroservices,
  fetchGraph,
  fetchServiceFile,
  generateMicroservice,
  resetWorkspace,
  scanRepository,
  uploadSessionFiles,
} from "../api";

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

function createInitialPipeline() {
  return {
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
      upload: "idle",
    },
    error: null,
  };
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

  const handleFilesPicked = async (event) => {
    const selectedFiles = Array.from(event.target.files || []);
    if (selectedFiles.length === 0) return;

    const defaultName = deriveProjectNameFromFiles(selectedFiles);
    const session = store.createSession({
      name: defaultName,
      sourceType: "upload",
      sourceLabel: "local file or folder",
      files: selectedFiles,
    });

    // Reset the file input so re-uploading the same folder works
    event.target.value = "";

    // --- Upload files to the backend and get the server-side repo path ---
    updatePipeline(session.id, (pipeline) => ({
      ...pipeline,
      actionState: { ...pipeline.actionState, upload: "running" },
    }));
    store.setSessionStatus(session.id, "uploading");

    try {
      const data = await uploadSessionFiles(session.id, selectedFiles);

      // Store the backend repo path so Scan uses it automatically
      const serverRepoPath = data.repo_path || "";
      store.setSessionRepoPath(session.id, serverRepoPath);

      store.addMessage(session.id, {
        role: "assistant",
        content: `Uploaded ${selectedFiles.length} file${selectedFiles.length === 1 ? "" : "s"} to the server. ${data.functions ?? 0} functions detected across ${data.files?.length ?? 0} source files. Click **Scan** to run the full analysis pipeline.`,
      });

      // If ingest already found functions, mark scan as done
      if (data.functions && data.functions > 0) {
        updatePipeline(session.id, (pipeline) => ({
          ...pipeline,
          scanSummary: {
            functions: data.functions ?? 0,
            dependencies: data.edges ?? 0,
            repoPath: serverRepoPath,
          },
          actionState: {
            ...pipeline.actionState,
            upload: "success",
            scan: "success",
          },
        }));
        store.setSessionStatus(session.id, "scan complete");
      } else {
        updatePipeline(session.id, (pipeline) => ({
          ...pipeline,
          actionState: { ...pipeline.actionState, upload: "success" },
        }));
        store.setSessionStatus(session.id, "uploaded");
      }
    } catch (error) {
      console.error(error);
      store.addMessage(session.id, {
        role: "assistant",
        content: `Upload failed: ${error.message}. You can still enter a local repo path manually and click Scan.`,
      });
      updatePipeline(session.id, (pipeline) => ({
        ...pipeline,
        error: error.message,
        actionState: { ...pipeline.actionState, upload: "error" },
      }));
      store.setSessionStatus(session.id, "error");
    }
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

  const handleDeleteSession = (sessionId) => {
    store.deleteSession(sessionId);
  };

  const updatePipeline = (sessionId, updater) => {
    store.updateSession(sessionId, (session) => ({
      ...session,
      pipeline: typeof updater === "function" ? updater(session.pipeline ?? createInitialPipeline()) : updater,
    }));
  };

  const setPipelineAction = (sessionId, action, status) => {
    updatePipeline(sessionId, (pipeline) => ({
      ...pipeline,
      actionState: {
        ...pipeline.actionState,
        [action]: status,
      },
    }));
  };

  const handleRepoPathChange = (sessionId, repoPath) => {
    store.setSessionRepoPath(sessionId, repoPath);
  };

  const handleSelectCluster = (sessionId, clusterName) => {
    updatePipeline(sessionId, (pipeline) => ({
      ...pipeline,
      selectedCluster: clusterName,
    }));
  };

  const handleScan = async () => {
    const session = store.activeSession;
    if (!session) return;

    const repoPath = session.repoPath.trim();

    if (!repoPath) {
      store.addMessage(session.id, {
        role: "assistant",
        content: "No repository path set. Upload a folder first, or enter a local repo path manually.",
      });
      return;
    }

    setPipelineAction(session.id, "scan", "running");
    store.setSessionStatus(session.id, "scanning");

    try {
      const data = await scanRepository(repoPath);

      updatePipeline(session.id, (pipeline) => ({
        ...createInitialPipeline(),
        scanSummary: {
          functions: data.functions ?? 0,
          dependencies: data.edges ?? 0,
          repoPath: data.repo_path ?? repoPath,
        },
        actionState: {
          ...createInitialPipeline().actionState,
          scan: "success",
        },
      }));

      store.addMessage(session.id, {
        role: "assistant",
        content: `Scanned successfully. Found ${data.functions ?? 0} functions and ${data.edges ?? 0} dependencies.`,
      });
      store.setSessionStatus(session.id, "scan complete");
    } catch (error) {
      console.error(error);
      updatePipeline(session.id, (pipeline) => ({
        ...pipeline,
        error: error.message,
        actionState: {
          ...pipeline.actionState,
          scan: "error",
        },
      }));
      store.addMessage(session.id, {
        role: "assistant",
        content: `Scan failed: ${error.message}`,
      });
      store.setSessionStatus(session.id, "error");
    }
  };

  const handleCalculateMicroservices = async () => {
    const session = store.activeSession;
    if (!session) return;

    setPipelineAction(session.id, "cluster", "running");
    store.setSessionStatus(session.id, "clustering");

    try {
      const clusterData = await calculateMicroservices();
      const graphData = await fetchGraph().catch(() => null);

      const clusterNames = Object.keys(clusterData.clusters || {});

      updatePipeline(session.id, (pipeline) => ({
        ...pipeline,
        clusterSummary: {
          clusterCount: clusterData.cluster_count ?? clusterNames.length,
          clusters: clusterData.clusters ?? {},
        },
        graph: graphData,
        selectedCluster: clusterNames[0] ?? pipeline.selectedCluster,
        error: null,
        actionState: {
          ...pipeline.actionState,
          cluster: "success",
        },
      }));

      store.addMessage(session.id, {
        role: "assistant",
        content: `Microservice boundaries calculated successfully. Found ${clusterData.cluster_count ?? clusterNames.length} distinct service clusters.`,
      });
      store.setSessionStatus(session.id, "clusters ready");
    } catch (error) {
      console.error(error);
      updatePipeline(session.id, (pipeline) => ({
        ...pipeline,
        error: error.message,
        actionState: {
          ...pipeline.actionState,
          cluster: "error",
        },
      }));
      store.addMessage(session.id, {
        role: "assistant",
        content: `Microservice calculation failed: ${error.message}`,
      });
      store.setSessionStatus(session.id, "error");
    }
  };

  const handleGenerateMicroservice = async () => {
    const session = store.activeSession;
    if (!session) return;

    const repoPath = session.repoPath.trim();
    const selectedCluster = session.pipeline?.selectedCluster;

    if (!selectedCluster) {
      store.addMessage(session.id, {
        role: "assistant",
        content: "Select a cluster from the graph before generating a microservice.",
      });
      return;
    }

    setPipelineAction(session.id, "generate", "running");
    store.setSessionStatus(session.id, "generating");

    try {
      const generated = await generateMicroservice(selectedCluster, repoPath);
      const serviceName = generated.dir;
      const preferredFile = generated.files.find((fileName) => fileName === "main.py") || generated.files[0];
      const fileContent = preferredFile
        ? await fetchServiceFile(serviceName, preferredFile)
        : { content: "" };

      updatePipeline(session.id, (pipeline) => ({
        ...pipeline,
        generatedService: {
          cluster: generated.cluster,
          serviceName: generated.service_name,
          dir: generated.dir,
          files: generated.files,
          activeFile: preferredFile ?? null,
          code: fileContent.content ?? "",
        },
        error: null,
        actionState: {
          ...pipeline.actionState,
          generate: "success",
        },
      }));

      store.addMessage(session.id, {
        role: "assistant",
        content: `Generated ${generated.service_name} from ${generated.cluster}.`,
      });
      store.setSessionStatus(session.id, "generation complete");
    } catch (error) {
      console.error(error);
      updatePipeline(session.id, (pipeline) => ({
        ...pipeline,
        error: error.message,
        actionState: {
          ...pipeline.actionState,
          generate: "error",
        },
      }));
      store.addMessage(session.id, {
        role: "assistant",
        content: `Microservice generation failed: ${error.message}`,
      });
      store.setSessionStatus(session.id, "error");
    }
  };

  const handleResetWorkspace = async () => {
    try {
      if (store.activeSessionId) {
        setPipelineAction(store.activeSessionId, "reset", "running");
      }

      await resetWorkspace();
      store.clearAllSessions();
      setSearchQuery("");
    } catch (error) {
      console.error(error);

      if (store.activeSessionId) {
        updatePipeline(store.activeSessionId, (pipeline) => ({
          ...pipeline,
          error: error.message,
          actionState: {
            ...pipeline.actionState,
            reset: "error",
          },
        }));
        store.setSessionStatus(store.activeSessionId, "error");
      }
    }
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
                onDeleteSession={handleDeleteSession}
                onToggleSidebar={handleToggleSidebar}
                onRepoPathChange={handleRepoPathChange}
                onScan={handleScan}
                onCalculateMicroservices={handleCalculateMicroservices}
                onGenerateMicroservice={handleGenerateMicroservice}
                onResetWorkspace={handleResetWorkspace}
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
              <ResultsPanel
                session={store.activeSession}
                onSelectCluster={handleSelectCluster}
              />
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