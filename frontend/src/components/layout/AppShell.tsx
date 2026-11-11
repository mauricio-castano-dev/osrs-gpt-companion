import { useState } from "react";
import { Backpack } from "lucide-react";
import { AppProvider } from "@/api/AppContext";
import type { Section } from "@/types/osrs";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { TopAppBar } from "./TopAppBar";
import { BottomNav } from "./BottomNav";
import { SkillsGrid } from "@/features/character/SkillsGrid";
import { RunsTracker } from "@/features/character/RunsTracker";
import { DailiesCard } from "@/features/character/DailiesCard";
import { BankDrawer } from "@/features/progress/BankDrawer";
import { ProgressExplorer } from "@/features/progress/ProgressExplorer";
import { DirectOracle } from "@/features/oracle/DirectOracle";
import { GearAndSlayer } from "@/features/progress/GearAndSlayer";
import { NotesSheet } from "@/features/notes/NotesSheet";
import { ChatView } from "@/features/chat/ChatView";
function Shell() {
  const [view, navigate] = useState<Section>("chat"),
    [bank, setBank] = useState(false),
    [noteCount, setNoteCount] = useState(0);
  const panel = view === "chat" ? "state" : view === "oracle" ? "gear" : view;
  return (
    <div className="app-shell">
      <TopAppBar navigate={navigate} openBank={() => setBank(true)} />
      <BankDrawer open={bank} onOpenChange={setBank} />
      <main className="workspace" data-view={view}>
        <aside className="side-panel">
          <Tabs
            value={panel}
            onValueChange={(value) => navigate(value as Section)}
          >
            <TabsList className="desktop-tabs" aria-label="Panel del personaje">
              <TabsTrigger id="tab-state" value="state">
                Habilidades & Runs
              </TabsTrigger>
              <TabsTrigger id="tab-gear" value="gear">
                Equipo & Progreso
              </TabsTrigger>
              <TabsTrigger id="tab-memory" value="memory">
                Memorias <span id="memory-count">({noteCount})</span>
              </TabsTrigger>
            </TabsList>
            <TabsContent
              id="state-content"
              value="state"
              forceMount
              hidden={panel !== "state"}
            >
              <SkillsGrid />
              <RunsTracker />
              <DailiesCard />
            </TabsContent>
            <TabsContent
              id="gear-content"
              value="gear"
              forceMount
              hidden={panel !== "gear"}
            >
              <div className="bank-access">
                <Button variant="outline" onClick={() => setBank(true)}>
                  <Backpack size={17} />
                  Banco & Inventario
                </Button>
                <span className="caption">LOCAL · EN RAM</span>
              </div>
              <div className="progress-primary">
                <ProgressExplorer />
              </div>
              <div className="oracle-feature">
                <DirectOracle />
              </div>
              <GearAndSlayer />
            </TabsContent>
            <TabsContent
              id="memory-content"
              value="memory"
              forceMount
              hidden={panel !== "memory"}
            >
              <NotesSheet onCount={setNoteCount} />
            </TabsContent>
          </Tabs>
        </aside>
        <ChatView />
      </main>
      <BottomNav active={view} navigate={navigate} />
    </div>
  );
}
export function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}
