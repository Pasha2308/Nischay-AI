import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { Dashboard } from "./pages/Dashboard";
import { NewTest } from "./pages/NewTest";
import { LivePreview } from "./pages/LivePreview";
import { TestModules } from "./pages/TestModules";
import { Results } from "./pages/Results";
import { RunHistory } from "./pages/RunHistory";
import { IssuesTracker } from "./pages/IssuesTracker";
import { Analytics } from "./pages/Analytics";
import { Schedules } from "./pages/Schedules";
import { Alerts } from "./pages/Alerts";
import { Integrations } from "./pages/Integrations";
import { Settings } from "./pages/Settings";
import { useApi } from "./hooks/useApi";
import { useToast } from "./hooks/useToast";

export default function App() {
  const api = useApi();
  const toast = useToast();

  return (
    <Routes>
      <Route element={<Layout usingDemo={api.usingDemo} toasts={toast.toasts} />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/new-test" element={<NewTest />} />
        <Route path="/live" element={<LivePreview />} />
        <Route path="/live/:runId" element={<LivePreview />} />
        <Route path="/modules" element={<TestModules />} />
        <Route path="/results" element={<Results />} />
        <Route path="/results/:runId" element={<Results />} />
        <Route path="/history" element={<RunHistory />} />
        <Route path="/issues" element={<IssuesTracker />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/schedules" element={<Schedules />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/integrations" element={<Integrations />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
