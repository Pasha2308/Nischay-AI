import type { ExecutionSnapshot, ScanIssue, TaskResultEntry } from "../services/backend-service";

export type JobExecutionResultsProps = {
  snapshot: ExecutionSnapshot | null | undefined;
  issues: ScanIssue[];
  fallbackRiskLevel: string;
  pipelineExecutionSeconds: number | null | undefined;
  pipelineDurationSeconds: number | null | undefined;
};

function normalizeDecisionHeadline(decision: string | undefined): {
  headline: string;
  variant: "safe" | "caution" | "nogo" | "unknown";
} {
  const d = (decision ?? "").trim().toUpperCase();
  if (!d) return { headline: "—", variant: "unknown" };
  if (d.includes("DO NOT SHIP")) return { headline: "DO NOT SHIP", variant: "nogo" };
  if (d.includes("CAUTION")) return { headline: "CAUTION", variant: "caution" };
  if (d.includes("SAFE")) return { headline: "SAFE", variant: "safe" };
  return { headline: decision?.trim() || "—", variant: "unknown" };
}

function safeString(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  return String(v);
}

function defectListForTask(tr: TaskResultEntry): unknown[] {
  const raw = tr.defects;
  return Array.isArray(raw) ? raw : [];
}

function defectTitleFromDict(d: unknown): string {
  if (d != null && typeof d === "object" && "defect" in d) {
    const x = (d as { defect?: string; description?: string }).defect?.trim();
    if (x) return x.replace(/_/g, " ");
    const desc = (d as { description?: string }).description?.trim();
    if (desc) return desc.length > 120 ? `${desc.slice(0, 117)}…` : desc;
  }
  return "Issue";
}

/** Bands: 0–29 green, 30–69 yellow, 70+ red */
function riskScoreBand(score: number): "low" | "mid" | "high" {
  if (score >= 70) return "high";
  if (score >= 30) return "mid";
  return "low";
}

function riskScoreValueClass(score: number | undefined): string {
  if (score == null || Number.isNaN(score)) return "";
  const b = riskScoreBand(Math.max(0, Math.min(100, score)));
  return `execution-summary-v--risk-${b}`;
}

export function DecisionCard({ snapshot }: { snapshot: ExecutionSnapshot | null | undefined }) {
  const snap = snapshot ?? null;
  const { headline, variant } = normalizeDecisionHeadline(snap?.decision);
  const summary = safeString(snap?.summary).trim() || "No summary available for this run.";
  const rawScore = snap?.risk_score;
  const score =
    typeof rawScore === "number" && !Number.isNaN(rawScore) ? Math.max(0, Math.min(100, rawScore)) : null;
  const band = score !== null ? riskScoreBand(score) : "low";

  return (
    <div className={`card decision-card decision-card--${variant}`}>
      <div className="decision-card-label">Release decision</div>
      {score !== null ? (
        <div className={`decision-risk-score decision-risk-score--${band}`} aria-label={`Risk score ${score} out of 100`}>
          <span className="decision-risk-score-value">{score}</span>
          <span className="decision-risk-score-max">/100</span>
          <span className="decision-risk-score-label">risk score</span>
        </div>
      ) : null}
      <div className="decision-card-headline" aria-live="polite">
        {headline}
      </div>
      <p className="decision-card-summary muted">{summary}</p>
    </div>
  );
}

export function ExecutionSummarySection({
  snapshot,
  fallbackRiskLevel,
  pipelineExecutionSeconds,
  pipelineDurationSeconds,
  issues,
  taskCount,
}: {
  snapshot: ExecutionSnapshot | null | undefined;
  fallbackRiskLevel: string;
  pipelineExecutionSeconds: number | null | undefined;
  pipelineDurationSeconds: number | null | undefined;
  issues: ScanIssue[];
  taskCount: number;
}) {
  const snap = snapshot ?? null;
  const risk = safeString(snap?.risk).trim() || fallbackRiskLevel || "—";
  const rs = snap?.risk_score;
  const scoreNum = typeof rs === "number" && !Number.isNaN(rs) ? Math.max(0, Math.min(100, rs)) : undefined;
  const riskScoreStr = scoreNum !== undefined ? `${Math.round(scoreNum)}/100` : "—";
  const dur =
    typeof snap?.duration === "number" && !Number.isNaN(snap.duration)
      ? `${snap.duration.toFixed(2)}s`
      : typeof pipelineExecutionSeconds === "number"
        ? `${pipelineExecutionSeconds.toFixed(2)}s`
        : typeof pipelineDurationSeconds === "number"
          ? `${pipelineDurationSeconds.toFixed(2)}s`
          : "—";
  const defectsCount = Array.isArray(snap?.defects) ? snap.defects.length : issues.length;
  const tasks = taskCount >= 0 ? taskCount : 0;

  const rows: { label: string; value: string }[] = [
    { label: "Risk score", value: riskScoreStr },
    { label: "Risk level", value: risk },
    { label: "Duration", value: dur },
    { label: "Total tasks run", value: String(tasks) },
    { label: "Total defects", value: String(defectsCount) },
  ];

  return (
    <div className="card execution-summary-card">
      <div className="card-title">Summary</div>
      <div className="execution-summary-grid">
        {rows.map((r) => (
          <div key={r.label} className="execution-summary-cell">
            <div className="execution-summary-k">{r.label}</div>
            <div
              className={`execution-summary-v ${r.label === "Risk score" ? riskScoreValueClass(scoreNum) : ""}`}
            >
              {r.value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function TaskResultsList({ taskResults }: { taskResults: TaskResultEntry[] | null | undefined }) {
  const list = Array.isArray(taskResults) ? taskResults : [];

  if (list.length === 0) {
    return (
      <div className="card task-results-card">
        <div className="card-title">Task results</div>
        <p className="muted">No per-task results for this run.</p>
      </div>
    );
  }

  return (
    <div className="card task-results-card">
      <div className="card-title">Task results</div>
      <ul className="task-results-list">
        {list.map((tr, idx) => {
          const name = safeString(tr.task).trim() || `task_${idx + 1}`;
          const ok = tr.success === true;
          const impact = safeString(tr.impact).trim().toUpperCase() || "—";
          const defects = defectListForTask(tr);
          return (
            <li key={`${name}-${idx}`} className="task-result-item">
              <div className="task-result-top">
                <span className="task-result-name">{name}</span>
                <span className={`badge task-result-status ${ok ? "low" : "critical"}`}>
                  {ok ? "success" : "failure"}
                </span>
                <span className="task-result-impact" title="Impact">
                  {impact}
                </span>
              </div>
              {defects.length > 0 ? (
                <ul className="task-result-defects">
                  {defects.map((d, di) => (
                    <li key={di} className="task-result-defect-line">
                      {defectTitleFromDict(d)}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted task-result-no-defects">No defects recorded for this task.</p>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function ExecutionLogsPanel({ logs }: { logs: string[] | null | undefined }) {
  const lines = Array.isArray(logs) ? logs.filter((l) => typeof l === "string") : [];

  return (
    <div className="card execution-logs-card">
      <div className="card-title">Execution logs</div>
      <p className="muted execution-logs-hint">Messages from the QA emit stream for this run.</p>
      <div className="execution-logs-panel" role="log" aria-label="Execution logs">
        {lines.length === 0 ? (
          <div className="muted execution-logs-empty">No emit logs captured.</div>
        ) : (
          lines.map((line, i) => (
            <div key={`${i}-${line.slice(0, 24)}`} className="execution-log-line">
              {line}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export function JobExecutionResults(props: JobExecutionResultsProps) {
  const { snapshot, issues, fallbackRiskLevel, pipelineExecutionSeconds, pipelineDurationSeconds } = props;
  const snap = snapshot ?? null;
  const taskResults: TaskResultEntry[] = Array.isArray(snap?.task_results) ? snap.task_results : [];
  const taskCount = taskResults.length;

  return (
    <div className="job-execution-results">
      <DecisionCard snapshot={snap} />
      <ExecutionSummarySection
        snapshot={snap}
        fallbackRiskLevel={fallbackRiskLevel}
        pipelineExecutionSeconds={pipelineExecutionSeconds}
        pipelineDurationSeconds={pipelineDurationSeconds}
        issues={issues}
        taskCount={taskCount}
      />
      <TaskResultsList taskResults={taskResults} />
      <ExecutionLogsPanel logs={snap?.logs} />
    </div>
  );
}
