export type StartScanResponse = {
	status: 'started';
	job_id: string;
	message: string;
};

export type ScanIssue = {
	type?: string;
	defect?: string;
	severity?: string;
	message?: string;
	test_id?: string;
	phase?: string;
	step_index?: number;
	action_type?: string;
	selector?: string | null;
	assertion_type?: string;
};

export type IssuesBySeverity = {
	critical: ScanIssue[];
	high: ScanIssue[];
	medium: ScanIssue[];
	low: ScanIssue[];
};

export type ScanSummary = {
	total_pages_scanned: number;
	total_actions_run: number;
	total_issues_found: number;
};

/** Payload stored in `LatestResultsResponse.result` when a scan completes */
export type ScanResultPayload = {
	summary?: ScanSummary;
	risk_score?: number;
	risk_level?: 'HIGH RISK' | 'MEDIUM RISK' | 'LOW RISK';
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
};

export type LatestResultsResponse = {
	job_id?: string | null;
	status: 'none' | 'started' | 'completed' | 'failed' | 'unknown';
	started_at?: number | null;
	completed_at?: number | null;
	result?: ScanResultPayload | null;
	error?: string | null;
};

export function flattenIssuesBySeverity(ibs: IssuesBySeverity | undefined): Array<ScanIssue & { _bucket: keyof IssuesBySeverity }> {
	if (!ibs) return [];
	const order: (keyof IssuesBySeverity)[] = ['critical', 'high', 'medium', 'low'];
	const out: Array<ScanIssue & { _bucket: keyof IssuesBySeverity }> = [];
	for (const bucket of order) {
		for (const issue of ibs[bucket] ?? []) {
			out.push({ ...issue, _bucket: bucket });
		}
	}
	return out;
}

const API_BASE = 'http://localhost:3000';

export const triggerTestRun = async (url: string): Promise<StartScanResponse> => {
	const response = await fetch(`${API_BASE}/jobs/test.run`, {
		headers: { 'Content-Type': 'application/json' },
		method: 'POST',
		body: JSON.stringify({ url })
	});

	if (!response.ok) {
		throw new Error(`Failed to start scan (${response.status})`);
	}

	return response.json();
};

export const fetchLatestResults = async (): Promise<LatestResultsResponse> => {
	const response = await fetch(`${API_BASE}/results`, { method: 'GET' });
	if (!response.ok) {
		throw new Error(`Failed to fetch results (${response.status})`);
	}
	return response.json();
};

export const fetchDemo = async (): Promise<ScanResultPayload> => {
	const response = await fetch(`${API_BASE}/demo`, { method: 'GET' });
	if (!response.ok) {
		throw new Error(`Failed to fetch demo (${response.status})`);
	}
	return response.json();
};
