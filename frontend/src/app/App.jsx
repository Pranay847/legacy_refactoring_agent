import { useState } from "react";
import Sidebar from "../components/Sidebar";
import SessionHeader from "../components/SessionHeader";
import UploadPanel from "../components/UploadPanel";
import ChatWindow from "../components/ChatWindow";
import ResultsPanel from "../components/ResultsPanel";
import NewSessionModal from "../components/NewSessionModal";
import useSessionStore from "../hooks/useSessionStore";

export default function App() {
  const store = useSessionStore();
  const [isNewSessionModalOpen, setIsNewSessionModalOpen] = useState(false);

  const handleOpenCreateSession = () => {
    setIsNewSessionModalOpen(true);
  };

  const handleCloseCreateSession = () => {
    setIsNewSessionModalOpen(false);
  };

  const handleCreateSession = (sessionName) => {
    store.createSession(sessionName);
    setIsNewSessionModalOpen(false);
  };

  return (
    <div className="h-screen bg-zinc-100 dark:bg-zinc-600">
      <div className="flex h-full">
        <Sidebar
          sessions={store.sessions}
          activeSessionId={store.activeSessionId}
          onSelect={store.setActiveSessionId}
          onCreate={handleOpenCreateSession}
        />

        <main className="flex min-w-0 flex-1 flex-col">
          <SessionHeader session={store.activeSession} />

          <div className="grid min-h-0 flex-1 grid-cols-1 gap-6 p-6 xl:grid-cols-[1.4fr_1fr]">
            <div className="flex min-h-0 flex-col gap-6">
              <UploadPanel
                session={store.activeSession}
                setSessionFiles={store.setSessionFiles}
                setSessionResults={store.setSessionResults}
                setSessionStatus={store.setSessionStatus}
              />

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
        isOpen={isNewSessionModalOpen}
        onClose={handleCloseCreateSession}
        onCreate={handleCreateSession}
      />
    </div>
  );
}