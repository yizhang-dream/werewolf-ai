import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import SetupWizard from "./components/GameSetup/SetupWizard";
import GameBoard from "./components/GameBoard/GameBoard";
import SettingsPanel from "./components/Settings/SettingsPanel";
import MemoryViewer from "./components/AgentMemory/MemoryViewer";
import GameListPage from "./components/GameReplay/GameListPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/setup" replace />} />
        <Route path="setup" element={<SetupWizard />} />
        <Route path="game/:gameId" element={<GameBoard />} />
        <Route path="replay/:gameId" element={<GameBoard />} />
        <Route path="games" element={<GameListPage />} />
        <Route path="settings" element={<SettingsPanel />} />
        <Route path="agents" element={<MemoryViewer />} />
      </Route>
    </Routes>
  );
}
