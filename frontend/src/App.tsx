import { Navigate, Route, Routes } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { DashboardPage } from "./pages/DashboardPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ScanHistoryPage } from "./pages/ScanHistoryPage";
import { DefectsPage } from "./pages/DefectsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { ScanDetailPage } from "./pages/ScanDetailPage";
import { JobResultsPage } from "./pages/JobResultsPage";
import { SyntheticDataPage } from "./pages/SyntheticDataPage";

export default function App() {
  return (
    <div className="layout">
      <Sidebar />
      <main className="content">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/history" element={<ScanHistoryPage />} />
          <Route path="/defects" element={<DefectsPage />} />
          <Route path="/synthetic" element={<SyntheticDataPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/scans/:id" element={<ScanDetailPage />} />
          <Route path="/results/:jobId" element={<JobResultsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

