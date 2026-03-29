import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchRunHistory, type RunHistoryEntry } from "../services/backend-service";

export function ScanHistoryPage() {
  const navigate = useNavigate();
  const [runs, setRuns] = useState<RunHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchRunHistory();
      setRuns(res.runs ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load run history");
      setRuns([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <div className="page">
        <h2>Run history</h2>
        <p className="muted">Loading…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <h2>Run history</h2>
        <div className="card empty-state">
          <p className="empty-state-title">{error}</p>
          <button type="button" className="btn-primary" onClick={() => void load()}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="page">
        <h2>Run history</h2>
        <div className="card empty-state">
          <p className="empty-state-title">No runs yet</p>
          <p className="muted" style={{ marginBottom: 16 }}>
            Completed scans appear here (last 10, this session only).
          </p>
          <button type="button" className="btn-primary" onClick={() => navigate("/")}>
            Launch a scan
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <h2>Run history</h2>
      <p className="muted" style={{ marginBottom: 12 }}>
        Last 10 runs (in-memory). Click a row to open results.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>URL</th>
              <th>Decision</th>
              <th>Time</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr
                key={r.job_id}
                className="clickable"
                onClick={() => navigate(`/results/${encodeURIComponent(r.job_id)}`)}
              >
                <td className="run-history-url">{r.url}</td>
                <td>{r.decision}</td>
                <td>{new Date(r.completed_at * 1000).toLocaleString()}</td>
                <td>{r.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
