import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchRunsList, type PersistedRunRow } from "../services/backend-service";

function statusBadgeClass(status: PersistedRunRow["status"]): string {
  if (status === "running") return "run-status run-status-running";
  if (status === "success") return "run-status run-status-success";
  return "run-status run-status-failed";
}

export function RunHistoryPage() {
  const navigate = useNavigate();
  const [runs, setRuns] = useState<PersistedRunRow[]>([]);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await fetchRunsList();
        if (!cancelled) setRuns(list);
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="page">
        <h2>Run History</h2>
        <p className="muted">Loading runs…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <h2>Run History</h2>
        <div className="card empty-state">
          <p>{error}</p>
          <p className="muted">Ensure the API is running on port 8000.</p>
        </div>
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="page">
        <h2>Run History</h2>
        <div className="card empty-state">
          <p>No runs recorded yet. Start a scan from the Dashboard.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <h2>Run History</h2>
      <p className="muted">Server-side history from <code>runs/registry.json</code>. Click a row for logs and report.</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Run ID</th>
              <th>URL</th>
              <th>Status</th>
              <th>Risk</th>
              <th>Started</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr
                key={r.run_id}
                className="clickable"
                onClick={() => navigate(`/runs/${encodeURIComponent(r.run_id)}`)}
              >
                <td><code>{r.run_id}</code></td>
                <td className="cell-ellipsis" title={r.target_url}>{r.target_url}</td>
                <td>
                  <span className={statusBadgeClass(r.status)}>{r.status}</span>
                  {r.partial && r.status === "success" ? (
                    <span className="run-partial-hint">partial</span>
                  ) : null}
                </td>
                <td>{r.risk_score ?? "—"}</td>
                <td>{new Date(r.start_time * 1000).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
