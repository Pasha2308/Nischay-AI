export type Severity = "critical" | "high" | "medium" | "low";

export type ScanIssue = {
  type?: string;
  defect?: string;
  severity?: Severity | string;
  message?: string;
  test_id?: string;
  phase?: string;
  step_index?: number;
  action_type?: string;
  selector?: string | null;
  assertion_type?: string;
};

export type IssuesBySeverity = Record<Severity, ScanIssue[]>;

export type ScanSummary = {
  total_pages_scanned: number;
  total_actions_run: number;
  total_issues_found: number;
};

export type ScanResultPayload = {
  summary?: ScanSummary;
  risk_score?: number;
  risk_level?: "HIGH RISK" | "MEDIUM RISK" | "LOW RISK";
  executive_summary?: string;
  issues_by_severity?: IssuesBySeverity;
  issues?: ScanIssue[];
  pages?: unknown[];
  actions_run?: unknown[];
  console_errors?: string[];
  failed_actions?: unknown[];
  missing_elements?: unknown[];
  run_id?: string | null;
  duration?: number;
  mode?: string;
  status?: string;
  warning?: string;
};

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

export type LatestResultsResponse = {
  job_id?: string | null;
  status:
    | "none"
    | "pending"
    | "running"
    | "started"
    | "WAITING_FOR_LOGIN"
    | "SCANNING"
    | "completed"
    | "partial"
    | "failed"
    | "unknown";
  started_at?: number | null;
  completed_at?: number | null;
  result?: ScanResultPayload | null;
  error?: string | null;
};

export type JobEvent = {
  time: number;
  type: "action" | "detection" | "error" | "success" | string;
  message: string;
};

export type JobStatusResponse = {
  job_id: string;
  status: "QUEUED" | "RUNNING" | "WAITING_FOR_LOGIN" | "SCANNING" | "PARTIAL" | "COMPLETE" | "FAILED";
  message: string;
  progress: number;
};

const API_BASE = "http://localhost:8000";

export async function triggerTestRun(url: string, auth?: ScanAuthPayload): Promise<StartScanResponse> {
  const response = await fetch(`${API_BASE}/jobs/test.run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(auth ? { url, auth } : { url }),
  });
  if (!response.ok) throw new Error(`Failed to start scan (${response.status})`);
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

export async function fetchDemo(): Promise<ScanResultPayload> {
  const response = await fetch(`${API_BASE}/demo`);
  if (!response.ok) throw new Error(`Failed to fetch demo (${response.status})`);
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
