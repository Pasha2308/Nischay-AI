export type Severity = "critical" | "high" | "medium" | "low";

export type ScanIssue = {
  /** Clear headline when provided by the API */
  title?: string;
  type?: string;
  defect?: string;
  severity?: Severity | string;
  message?: string;
  /** Canonical defect schema fields (always populated by backend for defects). */
  description?: string;
  element?: string;
  user_view?: string;
  how_to_fix?: string;
  test_id?: string;
  phase?: string;
  step_index?: number;
  action_type?: string;
  selector?: string | null;
  assertion_type?: string;
  /** Page URL where the issue was found */
  page_url?: string;
  /** One of: revenue | trust | ux | compliance | performance */
  business_impact?: string;
  /** Back-compat; prefer `how_to_fix` */
  fix_suggestion?: string;
};

export type PipelineMetricsPayload = {
  total_scan_time?: number;
  crawl_time?: number | null;
  execution_time?: number | null;
  retries_count?: number;
  step_retries?: number;
  pages_scanned?: number | null;
  /** Human-readable executed scope: micro-task name, flow list, or preset group. */
  task?: string | null;
};

export type ActionTrailEntry = {
  id?: string;
  phase?: string;
  action_type?: string;
  description?: string;
  target_url?: string;
  target_element?: string;
  input_value?: string;
  outcome?: string;
  outcome_detail?: string;
  screenshot_path_before?: string;
  screenshot_path_after?: string;
  screenshot_path?: string;
  duration_ms?: number;
  defect_triggered?: string | null;
};

export type IssuesBySeverity = Record<Severity, ScanIssue[]>;

export type TaskResultEntry = {
  task?: string;
  success?: boolean;
  impact?: string;
  defects?: unknown[];
};

/** Stable execution payload from orchestrator (matches backend ``execution_snapshot``). */
export type ExecutionSnapshot = {
  url?: string;
  decision?: string;
  risk?: string;
  /** 0–100 from failed-task impact weights (backend decision engine). */
  risk_score?: number;
  summary?: string;
  task_results?: TaskResultEntry[];
  defects?: unknown[];
  logs?: string[];
  duration?: number;
};

export type ScanSummary = {
  total_pages_scanned: number;
  total_actions_run: number;
  total_issues_found: number;
};

export type RiskBand = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export type ScanResultPayload = {
  /** Authoritative crawl page count (matches ``pages.length``). */
  pages_scanned?: number;
  pages?: unknown[];
  summary?: ScanSummary;
  risk_score?: number;
  /** Display label (e.g. Critical, High). */
  risk_level?: string;
  risk_level_legacy?: string;
  /** New formula: ``{ score, level }`` with level CRITICAL | HIGH | MEDIUM | LOW. */
  risk?: { score: number; level: RiskBand };
  executive_summary?: string;
  issues_by_severity?: IssuesBySeverity;
  issues?: ScanIssue[];
  actions_run?: unknown[];
  console_errors?: string[];
  failed_actions?: unknown[];
  missing_elements?: unknown[];
  run_id?: string | null;
  duration?: number;
  /** Convenience metric for UI: pipeline duration in seconds. */
  test_duration_seconds?: number;
  mode?: string;
  status?: string;
  warning?: string;
  scan_mode?: string;
  scan_task?: string;
  pipeline_metrics?: PipelineMetricsPayload | null;
  /** Micro-task run snapshot: decision, defects, emit logs, per-task results. */
  execution_snapshot?: ExecutionSnapshot | null;
};

/** Prefer top-level ``pages_scanned`` from API; ``summary.total_pages_scanned`` is fallback only. */
export function pagesScannedFromResult(result: ScanResultPayload | null | undefined): number {
  if (result == null) return 0;
  if (typeof result.pages_scanned === "number") return result.pages_scanned;
  return result.summary?.total_pages_scanned ?? 0;
}

export type SyntheticDomain = "ecommerce" | "healthcare" | "finance" | "auth";

export type SyntheticGenerateResponse = {
  domain: SyntheticDomain;
  count: number;
  rows: Record<string, string | number>[];
};

export type StartScanResponse = {
  status: "started";
  job_id: string;
  message: string;
};

export type ScanAuthPayload = {
  username: string;
  password: string;
};

export type ScanCredentialsPayload = {
  username: string;
  password: string;
  /** Page to open for login (defaults to scan URL if omitted). */
  login_url?: string;
};

export type DashboardSummary = {
  total_runs: number;
  last_decision: string | null;
  last_job_id: string | null;
  pass_count: number;
  fail_count: number;
};

export type RunHistoryEntry = {
  job_id: string;
  url: string;
  decision: string;
  completed_at: number;
  status: string;
};

export type RunHistoryResponse = {
  runs: RunHistoryEntry[];
};

export type LatestResultsResponse = {
  job_id?: string | null;
  status:
    | "none"
    | "pending"
    | "running"
    | "started"
    | "WAITING_FOR_LOGIN"
    | "SCANNING"
    | "complete"
    | "completed"
    | "partial"
    | "failed"
    | "unknown";
  started_at?: number | null;
  completed_at?: number | null;
  result?: ScanResultPayload | null;
  error?: string | null;
  scan_mode?: "fast" | "deep" | string | null;
  scan_task?: string | null;
};

export type JobEvent = {
  time: number;
  type: "action" | "detection" | "error" | "success" | "stage" | "crawler" | "execution" | "evaluator" | string;
  message: string;
  /** Sub-type for structured pipeline events (e.g. crawl_start, execution_complete). */
  name?: string;
  payload?: Record<string, unknown>;
};

export type JobStatusResponse = {
  job_id: string;
  status: "QUEUED" | "RUNNING" | "WAITING_FOR_LOGIN" | "SCANNING" | "PARTIAL" | "COMPLETE" | "FAILED";
  message: string;
  progress: number;
};

const API_BASE = "http://localhost:8000";

export type TriggerTestRunOptions = {
  auth?: ScanAuthPayload;
  scan_mode?: string;
  scan_task?: string;
  /** Explicit flow ids (overrides scan_task when non-empty). */
  flows?: string[];
  /** Single fast task when set with micro_task. */
  task_type?: string;
  micro_task?: string;
  requires_login?: boolean;
  credentials?: ScanCredentialsPayload;
  /** Playwright browser; default chromium. */
  browser_type?: "chromium" | "firefox" | "webkit";
  /** Optional natural-language intent, e.g. "search for shoes". */
  task_input?: string;
};

export async function triggerTestRun(
  url: string,
  options?: TriggerTestRunOptions,
): Promise<StartScanResponse> {
  const body: Record<string, unknown> = { url };
  if (options?.auth) body.auth = options.auth;
  if (options?.scan_mode != null && options.scan_mode !== "") body.scan_mode = options.scan_mode;
  if (options?.scan_task != null && options.scan_task !== "") body.scan_task = options.scan_task;
  if (options?.flows != null && options.flows.length > 0) body.flows = options.flows;
  if (options?.task_type != null && options.task_type !== "") body.task_type = options.task_type;
  if (options?.micro_task != null && options.micro_task !== "") body.micro_task = options.micro_task;
  if (options?.requires_login !== undefined) body.requires_login = options.requires_login;
  if (options?.credentials) body.credentials = options.credentials;
  if (options?.browser_type) body.browser_type = options.browser_type;
  if (options?.task_input != null && options.task_input.trim() !== "") {
    body.task_input = options.task_input.trim();
  }
  const response = await fetch(`${API_BASE}/jobs/test.run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`Failed to start scan (${response.status})`);
  return response.json();
}

export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  const response = await fetch(`${API_BASE}/dashboard/summary`);
  if (!response.ok) throw new Error(`Failed to load dashboard (${response.status})`);
  return response.json();
}

export async function fetchRunHistory(): Promise<RunHistoryResponse> {
  const response = await fetch(`${API_BASE}/runs/history`);
  if (!response.ok) throw new Error(`Failed to fetch run history (${response.status})`);
  return response.json();
}

export async function fetchLatestResults(): Promise<LatestResultsResponse> {
  const response = await fetch(`${API_BASE}/results`);
  if (!response.ok) throw new Error(`Failed to fetch results (${response.status})`);
  return response.json();
}

export async function fetchResults(jobId: string): Promise<LatestResultsResponse> {
  const response = await fetch(`${API_BASE}/results/${jobId}`);
  if (!response.ok) throw new Error(`Failed to fetch job results (${response.status})`);
  return response.json();
}

export async function fetchJobEvents(jobId: string): Promise<JobEvent[]> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/events`);
  if (!response.ok) throw new Error(`Failed to fetch job events (${response.status})`);
  const payload = (await response.json()) as { job_id: string; events: JobEvent[] };
  return payload.events ?? [];
}

export async function fetchJobStatus(jobId: string): Promise<JobStatusResponse> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/status`);
  if (!response.ok) throw new Error(`Failed to fetch job status (${response.status})`);
  return response.json();
}

export async function generateSynthetic(domain: SyntheticDomain, count: number): Promise<SyntheticGenerateResponse> {
  const response = await fetch(`${API_BASE}/synthetic/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ domain, count }),
  });
  if (!response.ok) throw new Error(`Failed to generate synthetic data (${response.status})`);
  return response.json();
}
