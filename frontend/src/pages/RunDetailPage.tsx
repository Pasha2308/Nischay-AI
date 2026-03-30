import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  fetchRunCompare,
  fetchRunDetail,
  fetchRunLogsText,
  type PersistedRunRow,
  type ScanResultPayload,
} from "../services/backend-service";

function badgeClass(status: PersistedRunRow["status"]): string {
  if (status === "running") return "run-status run-status-running";
  if (status === "success") return "run-status run-status-success";
  return "run-status run-status-failed";
}

export function RunDetailPage() {
  const { runId = "" } = useParams<{ runId: string }>();
  const decoded = decodeURIComponent(runId);
  const [run, setRun] = useState<PersistedRunRow | null>(null);
  const [result, setResult] = useState<ScanResultPayload | null>(null);
  const [logs, setLogs] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareJson, setCompareJson] = useState<string>("");
  const [compareError, setCompareError] = useState<string>("");

  useEffect(() => {
    if (!decoded) return;
    let cancelled = false;
    (async () => {
      try {
        const detail = await fetchRunDetail(decoded);
        if (cancelled) return;
        setRun(detail.run);
        setResult(detail.result);
        const logText = await fetchRunLogsText(decoded);
        if (!cancelled) setLogs(logText);
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [decoded]);

  if (!decoded) {
    return (
      <div className="page">
        <p className="muted">Missing run id.</p>
        <Link to="/runs">Back to Run History</Link>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="page">
        <p className="muted">Loading run…</p>
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="page">
        <p>{error || "Run not found."}</p>
        <Link to="/runs">Back to Run History</Link>
      </div>
    );
  }

  async function onCompareLastRun() {
    setCompareLoading(true);
    setCompareError("");
    setCompareJson("");
    try {
      const data = await fetchRunCompare(decoded);
      setCompareJson(JSON.stringify(data, null, 2));
    } catch (e) {
      setCompareError(String(e));
    } finally {
      setCompareLoading(false);
    }
  }

  return (
    <div className="page">
      <div className="toolbar" style={{ justifyContent: "space-between" }}>
        <Link to="/runs" className="muted">← Run History</Link>
        <button type="button" onClick={onCompareLastRun} disabled={compareLoading}>
          {compareLoading ? "Comparing…" : "Compare with last run"}
        </button>
      </div>
      <h2>Run <code>{run.run_id}</code></h2>

      <div className="card">
        <div className="card-title">Summary</div>
        <dl className="run-detail-dl">
          <dt>URL</dt>
          <dd><a href={run.target_url} target="_blank" rel="noreferrer">{run.target_url}</a></dd>
          <dt>Status</dt>
          <dd>
            <span className={badgeClass(run.status)}>{run.status}</span>
            {run.partial ? <span className="run-partial-hint">partial outcome</span> : null}
          </dd>
          <dt>Job</dt>
          <dd><code>{run.job_id ?? "—"}</code></dd>
          <dt>Risk score</dt>
          <dd>{run.risk_score ?? "—"}</dd>
          <dt>Started</dt>
          <dd>{new Date(run.start_time * 1000).toLocaleString()}</dd>
          <dt>Ended</dt>
          <dd>{run.end_time ? new Date(run.end_time * 1000).toLocaleString() : "—"}</dd>
          <dt>Summary</dt>
          <dd>{run.summary ?? "—"}</dd>
          {run.error ? (
            <>
              <dt>Error</dt>
              <dd className="run-err">{run.error}</dd>
            </>
          ) : null}
        </dl>
      </div>

      {(compareError || compareJson) && (
        <div className="card">
          <div className="card-title">Baseline comparison</div>
          {compareError ? <p className="run-err">{compareError}</p> : null}
          {compareJson ? (
            <pre className="run-json-pre" style={{ maxHeight: 320, overflow: "auto" }}>
              {compareJson}
            </pre>
          ) : null}
        </div>
      )}

      {result ? (
        <div className="card">
          <div className="card-title">Report</div>
          {result.executive_summary ? (
            <div className="executive-card" style={{ marginBottom: 12 }}>
              <div className="muted" style={{ fontSize: 12 }}>Executive summary</div>
              <p style={{ margin: "8px 0 0" }}>{result.executive_summary}</p>
            </div>
          ) : null}
          <p className="muted">
            Risk level: {result.risk_level ?? "—"} · Issues:{" "}
            {result.summary?.total_issues_found ?? "—"}
          </p>
          <details className="run-json-details">
            <summary>Full result JSON</summary>
            <pre className="run-json-pre">{JSON.stringify(result, null, 2)}</pre>
          </details>
        </div>
      ) : (
        <div className="card">
          <div className="card-title">Report</div>
          <p className="muted">No result snapshot on disk for this run.</p>
        </div>
      )}

      <div className="card log-card">
        <div className="card-title">Logs</div>
        <div className="log-panel run-log-pre-wrap">
          <pre className="run-log-pre">{logs || "(empty)"}</pre>
        </div>
      </div>
    </div>
  );
}
