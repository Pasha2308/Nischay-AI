import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fetchDashboardSummary, type DashboardSummary } from "../services/backend-service";

export function DashboardPage() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDashboardSummary()
      .then((d) => {
        if (!cancelled) setSummary(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load dashboard");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const total = summary ? summary.pass_count + summary.fail_count : 0;
  const passPct = total > 0 ? Math.round((summary!.pass_count / total) * 100) : 0;
  const failPct = total > 0 ? 100 - passPct : 0;

  return (
    <div className="page dashboard-home">
      <header className="dashboard-home-header">
        <h1 className="dashboard-home-title">Dashboard</h1>
        <p className="muted dashboard-home-sub">Session overview — fast load, in-memory only.</p>
      </header>

      {error && (
        <div className="card dashboard-home-card">
          <p className="dashboard-home-error">{error}</p>
          <button type="button" className="btn-primary" onClick={() => window.location.reload()}>
            Retry
          </button>
        </div>
      )}

      {!error && !summary && (
        <p className="muted" aria-live="polite">
          Loading…
        </p>
      )}

      {!error && summary && (
        <>
          <div className="dashboard-home-grid">
            <div className="card dashboard-stat-card">
              <div className="dashboard-stat-label">Total runs</div>
              <div className="dashboard-stat-value">{summary.total_runs}</div>
            </div>
            <div className="card dashboard-stat-card">
              <div className="dashboard-stat-label">Last run decision</div>
              <div className="dashboard-stat-value dashboard-stat-value--decision">
                {summary.last_decision ?? "—"}
              </div>
              {summary.last_job_id && (
                <button
                  type="button"
                  className="dashboard-link-results"
                  onClick={() => navigate(`/results/${encodeURIComponent(summary.last_job_id!)}`)}
                >
                  Open results
                </button>
              )}
            </div>
          </div>

          <div className="card dashboard-home-card dashboard-chart-card">
            <div className="dashboard-chart-title">Pass vs fail (last 10 in memory)</div>
            {total === 0 ? (
              <p className="muted dashboard-chart-empty">No completed runs yet.</p>
            ) : (
              <>
                <div className="dashboard-chart-bar" role="img" aria-label={`Pass ${passPct} percent, fail ${failPct} percent`}>
                  <div
                    className="dashboard-chart-seg dashboard-chart-seg--pass"
                    style={{ width: `${passPct}%` }}
                  />
                  <div
                    className="dashboard-chart-seg dashboard-chart-seg--fail"
                    style={{ width: `${failPct}%` }}
                  />
                </div>
                <div className="dashboard-chart-legend">
                  <span>
                    <span className="dashboard-dot dashboard-dot--pass" /> Pass {summary.pass_count}
                  </span>
                  <span>
                    <span className="dashboard-dot dashboard-dot--fail" /> Fail {summary.fail_count}
                  </span>
                </div>
              </>
            )}
          </div>

          <div className="dashboard-home-actions">
            <button type="button" className="btn-primary dashboard-cta" onClick={() => navigate("/test")}>
              Run New Test
            </button>
          </div>

          <p className="muted dashboard-home-footer">
            <Link to="/history">Run history</Link>
            {" · "}
            <Link to="/test">Test launcher</Link>
          </p>
        </>
      )}
    </div>
  );
}
