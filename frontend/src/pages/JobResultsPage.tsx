import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { RiskGauge } from "../components/RiskGauge";
import {
  fetchResults,
  pagesScannedFromResult,
  type ActionTrailEntry,
  type LatestResultsResponse,
  type ScanIssue,
  type ScanResultPayload,
} from "../services/backend-service";

function riskLevelFromResult(result: ScanResultPayload | null | undefined): string {
  if (result?.risk?.level) return result.risk.level;
  return result?.risk_level ?? result?.risk_level_legacy ?? "LOW";
}

function riskBadgeClass(result: ScanResultPayload | null | undefined): string {
  const band = result?.risk?.level;
  const leg = result?.risk_level_legacy ?? "";
  if (band === "CRITICAL" || leg === "CRITICAL RISK") return "critical";
  if (band === "HIGH" || leg === "HIGH RISK") return "critical";
  if (band === "MEDIUM" || leg === "MEDIUM RISK") return "high";
  return "low";
}

function riskScoreFromResult(result: ScanResultPayload | null | undefined): number {
  return typeof result?.risk_score === "number" ? result.risk_score : 0;
}

function normalizeSeverity(s: string | undefined): string {
  const v = (s ?? "medium").toLowerCase();
  if (v === "critical" || v === "high" || v === "medium" || v === "low") return v;
  return "medium";
}

function defectTitle(issue: ScanIssue): string {
  const d = issue.defect?.trim();
  if (d) return d.replace(/_/g, " ");
  const t = issue.type?.trim();
  if (t) return t.replace(/_/g, " ");
  const msg = issue.message?.trim() ?? "";
  return msg.length > 120 ? `${msg.slice(0, 117)}…` : msg || "Issue";
}

function defectPage(issue: ScanIssue): string {
  const u = issue.page_url?.trim();
  if (u) return u;
  return "—";
}

function actionsTakenFromResult(result: ScanResultPayload): number {
  const n = result.summary?.total_actions_run;
  if (typeof n === "number") return n;
  const trail = result.action_trail;
  if (Array.isArray(trail)) return trail.length;
  const ar = result.actions_run;
  if (Array.isArray(ar)) return ar.length;
  return 0;
}

function issuesFoundFromResult(result: ScanResultPayload, issues: ScanIssue[]): number {
  const n = result.summary?.total_issues_found;
  if (typeof n === "number") return n;
  return issues.length;
}

function useAnimatedRiskScore(target: number, active: boolean): number {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (!active) {
      setValue(0);
      return;
    }
    setValue(0);
    const start = performance.now();
    const duration = 1200;
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - t) ** 3;
      setValue(Math.round(target * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active, target]);
  return value;
}

function TaskMetricsPanel({
  result,
  scanTask,
}: {
  result: ScanResultPayload;
  scanTask: string;
}) {
  const pm = result.pipeline_metrics;
  const rows: { label: string; value: string }[] = [];

  const mode = result.scan_mode ?? "—";
  rows.push({ label: "Scan mode", value: String(mode) });

  if (typeof result.duration === "number") {
    rows.push({ label: "Pipeline duration", value: `${result.duration.toFixed(1)}s` });
  }
  if (pm?.total_scan_time != null) {
    rows.push({ label: "Total scan time", value: `${pm.total_scan_time}s` });
  }
  if (pm?.crawl_time != null) {
    rows.push({ label: "Crawl time", value: `${pm.crawl_time}s` });
  }
  if (pm?.execution_time != null) {
    rows.push({ label: "Execution time", value: `${pm.execution_time}s` });
  }
  const retries = pm?.retries_count ?? pm?.step_retries;
  if (typeof retries === "number" && retries > 0) {
    rows.push({ label: "Step retries", value: String(retries) });
  }

  const taskBlurb: Record<string, string> = {
    full_app: "End-to-end coverage across discovered routes and flows.",
    full_app_scan: "Full user journey: auth, browse, product, cart, checkout, support, UI, navigation.",
    quick_scan: "Fast pass: UI integrity and navigation only.",
    conversion_scan: "Browse → product → cart → checkout funnel.",
    auth_scan: "Authentication and session flows only.",
    auth: "Prioritizes sign-in, session, and access-control surfaces.",
    checkout: "Emphasizes cart, payment, and order-completion paths.",
    forms: "Focuses on form validation, submission, and field-level defects.",
  };

  return (
    <div className="card job-metrics-card">
      <div className="card-title">Metrics</div>
      <p className="job-metrics-task muted">
        Task: <strong className="job-metrics-task-name">{scanTask}</strong>
      </p>
      <p className="job-metrics-blurb muted">
        {taskBlurb[scanTask] ?? taskBlurb.full_app_scan ?? taskBlurb.full_app}
      </p>
      <dl className="job-metrics-dl">
        {rows.map((r) => (
          <div key={r.label} className="job-metrics-row">
            <dt>{r.label}</dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function ActionTrailSection({ trail }: { trail: ActionTrailEntry[] }) {
  if (!trail.length) {
    return (
      <div className="card job-action-trail">
        <div className="card-title">Action Trail</div>
        <p className="muted">No recorded actions for this run.</p>
      </div>
    );
  }

  return (
    <div className="card job-action-trail">
      <div className="card-title">Action Trail</div>
      <p className="muted job-action-trail-hint">
        Expand a row to see outcome details and screenshot paths captured during the run.
      </p>
      <div className="action-trail-list">
        {trail.map((a, i) => {
          const before = a.screenshot_path_before || "";
          const after = a.screenshot_path_after || a.screenshot_path || "";
          const outcome = (a.outcome || "—").toLowerCase();
          return (
            <details key={a.id ?? `${i}-${a.description}`} className="action-trail-item">
              <summary className="action-trail-summary">
                <span className={`badge action-phase action-phase--${(a.phase || "execute").toLowerCase()}`}>
                  {a.phase ?? "—"}
                </span>
                <span className="action-trail-type">{a.action_type ?? "action"}</span>
                <span className="action-trail-desc">{a.description || "—"}</span>
                <span className={`badge outcome-pill outcome-pill--${outcome}`}>{a.outcome ?? "—"}</span>
              </summary>
              <div className="action-trail-body">
                {a.target_url ? (
                  <p className="action-trail-line">
                    <span className="action-trail-k">Page</span>
                    <span className="action-trail-v">{a.target_url}</span>
                  </p>
                ) : null}
                {a.target_element ? (
                  <p className="action-trail-line">
                    <span className="action-trail-k">Target</span>
                    <code className="action-trail-code">{a.target_element}</code>
                  </p>
                ) : null}
                {a.outcome_detail ? (
                  <p className="action-trail-line">
                    <span className="action-trail-k">Detail</span>
                    <span>{a.outcome_detail}</span>
                  </p>
                ) : null}
                {typeof a.duration_ms === "number" ? (
                  <p className="action-trail-line">
                    <span className="action-trail-k">Duration</span>
                    <span>{a.duration_ms} ms</span>
                  </p>
                ) : null}
                <div className="action-trail-shots">
                  {before ? (
                    <div className="action-shot">
                      <span className="action-trail-k">Before</span>
                      <span className="action-shot-path">{before}</span>
                    </div>
                  ) : null}
                  {after ? (
                    <div className="action-shot">
                      <span className="action-trail-k">After</span>
                      <span className="action-shot-path">{after}</span>
                    </div>
                  ) : null}
                  {!before && !after ? (
                    <p className="muted action-shot-none">No screenshots for this action.</p>
                  ) : null}
                </div>
              </div>
            </details>
          );
        })}
      </div>
    </div>
  );
}

export function JobResultsPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [data, setData] = useState<LatestResultsResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    setLoadError(null);
    setData(null);
    fetchResults(jobId)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setLoadError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  const result = data?.result ?? null;
  const status = (data?.status ?? "unknown").toLowerCase();
  const issues = result?.issues ?? [];
  const riskScore = riskScoreFromResult(result ?? undefined);
  const riskLevel = riskLevelFromResult(result ?? undefined);
  const badgeClass = riskBadgeClass(result ?? undefined);
  const scanTask = (data?.scan_task ?? result?.scan_task ?? "full_app").trim() || "full_app";
  const showResults =
    Boolean(data) &&
    (status === "complete" || status === "completed" || status === "partial") &&
    Boolean(result);
  const animateDial = Boolean(jobId && showResults && result);
  const animatedScore = useAnimatedRiskScore(riskScore, animateDial);
  const trail = (result?.action_trail ?? []) as ActionTrailEntry[];

  if (!jobId) {
    return (
      <div className="page">
        <p>Missing job id.</p>
        <Link to="/">Back to dashboard</Link>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="page">
        <p className="muted">Could not load results.</p>
        <p>{loadError}</p>
        <Link to="/">Back to dashboard</Link>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="page">
        <p className="muted">Loading results…</p>
      </div>
    );
  }

  return (
    <div className="page job-results-page">
      <p className="job-results-back">
        <Link to="/">← Launch</Link>
      </p>
      <header className="job-results-header">
        <h2 className="job-results-title">Scan results</h2>
        <p className="muted job-results-meta">
          Job <code>{jobId}</code>
          {data.started_at != null && (
            <>
              {" "}
              · Started {new Date(data.started_at * 1000).toLocaleString()}
            </>
          )}
        </p>
      </header>

      {status === "failed" && (
        <div className="card job-results-failed" style={{ borderLeft: "4px solid #dc2626" }}>
          <div className="card-title">Scan failed</div>
          <p>{data.error ?? "Pipeline did not return a scan result."}</p>
        </div>
      )}

      {showResults && result && (
        <div className="job-results-grid">
          <aside className="job-results-col job-results-col--left">
            <div className="card job-risk-card">
              <RiskGauge score={animatedScore} />
              <div className="job-risk-meta">
                <span className={`badge ${badgeClass}`}>{riskLevel}</span>
                <span className="muted">Risk band</span>
              </div>
            </div>
            <div className="card job-stats-card">
              <div className="card-title">Run stats</div>
              <dl className="job-stats-dl">
                <div className="job-stats-row">
                  <dt>Pages scanned</dt>
                  <dd>{pagesScannedFromResult(result)}</dd>
                </div>
                <div className="job-stats-row">
                  <dt>Actions taken</dt>
                  <dd>{actionsTakenFromResult(result)}</dd>
                </div>
                <div className="job-stats-row">
                  <dt>Issues found</dt>
                  <dd>{issuesFoundFromResult(result, issues)}</dd>
                </div>
              </dl>
            </div>
          </aside>

          <main className="job-results-col job-results-col--center">
            <div className="card job-defects-card">
              <div className="card-title">Defects</div>
              {issues.length === 0 ? (
                <div className="issues-empty issues-empty--in-card">
                  <p className="issues-empty-title">No issues found</p>
                  <p className="issues-empty-sub">Your app looks healthy for this run.</p>
                </div>
              ) : (
                <div className="defect-card-list">
                  {issues.map((issue, idx) => {
                    const sev = normalizeSeverity(String(issue.severity ?? "medium"));
                    const title = defectTitle(issue);
                    const page = defectPage(issue);
                    const impact =
                      issue.business_impact?.trim() ||
                      "Affects user experience and release confidence until addressed.";
                    const fix =
                      issue.fix_suggestion?.trim() ||
                      "Review the failing assertion or UI state on the page above.";
                    return (
                      <article
                        key={`${idx}-${issue.test_id ?? ""}-${issue.message?.slice(0, 24)}`}
                        className={`defect-card defect-card--${sev}`}
                      >
                        <div className="defect-card-head">
                          <span className={`badge ${sev}`}>{sev}</span>
                          <h3 className="defect-card-title">{title}</h3>
                        </div>
                        <p className="defect-card-page" title={page}>
                          {page}
                        </p>
                        <div className="defect-card-block">
                          <div className="defect-card-label">Business impact</div>
                          <p className="defect-card-text">{impact}</p>
                        </div>
                        <div className="defect-card-block">
                          <div className="defect-card-label">Fix suggestion</div>
                          <p className="defect-card-text">{fix}</p>
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </div>
            <ActionTrailSection trail={trail} />
          </main>

          <aside className="job-results-col job-results-col--right">
            <div className="card job-exec-card">
              <div className="card-title">Executive summary</div>
              <div className="job-exec-body">
                {result.executive_summary ?? (
                  <p className="muted">Executive summary will appear here when generated.</p>
                )}
              </div>
              {result.warning ? <p className="job-exec-warning">{result.warning}</p> : null}
            </div>
            <TaskMetricsPanel result={result} scanTask={scanTask} />
          </aside>
        </div>
      )}

      {status !== "failed" &&
        status !== "complete" &&
        status !== "completed" &&
        status !== "partial" && (
          <div className="card">
            <p className="muted">Job status: {data.status}</p>
            {!data.result ? <p>No result payload yet.</p> : null}
          </div>
        )}
    </div>
  );
}
