import type { ScanIssue, ScanResultPayload } from "./services/backend-service";

export type ScanStatus = "completed" | "failed" | "started";

export type ScanRecord = {
  id: string;
  projectId: string;
  projectName: string;
  url: string;
  date: string;
  status: ScanStatus;
  riskScore: number;
  riskLevel: "HIGH RISK" | "MEDIUM RISK" | "LOW RISK";
  defectCount: number;
  result: ScanResultPayload;
};

export type Project = {
  id: string;
  name: string;
  siteCount: number;
};

export function toScanRecord(
  input: Partial<ScanRecord> & { id: string; url: string; projectId?: string; projectName?: string; result?: ScanResultPayload },
): ScanRecord {
  const result = input.result ?? {};
  const riskScore = result.risk_score ?? 0;
  const defectCount = result.summary?.total_issues_found ?? result.issues?.length ?? 0;
  return {
    id: input.id,
    projectId: input.projectId ?? "p1",
    projectName: input.projectName ?? "Marketing Site",
    url: input.url,
    date: input.date ?? new Date().toISOString(),
    status: input.status ?? "completed",
    riskScore,
    riskLevel: result.risk_level ?? "LOW RISK",
    defectCount,
    result,
  };
}

export function allIssues(record: ScanRecord): ScanIssue[] {
  return record.result.issues ?? [];
}

