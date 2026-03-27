import type { Project, ScanRecord } from "../types";
import { toScanRecord } from "../types";

export const DEMO_PROJECTS: Project[] = [
  { id: "p1", name: "Marketing Site", siteCount: 1 },
  { id: "p2", name: "Shop Platform", siteCount: 1 },
  { id: "p3", name: "Docs Portal", siteCount: 1 },
];

const urls = [
  "https://amazon.com",
  "https://github.com",
  "https://stripe.com",
  "https://amazon.com/gp/cart/view.html",
  "https://github.com/features/actions",
  "https://stripe.com/docs/payments/checkout",
  "https://amazon.com/gp/help/customer/display.html",
  "https://github.com/pricing",
  "https://stripe.com/pricing",
  "https://amazon.com/ap/signin",
  "https://github.com/login",
  "https://stripe.com/login",
];

const severities = ["critical", "high", "medium", "low"] as const;

function fakeIssues(count: number) {
  return Array.from({ length: count }).map((_, i) => {
    const sev = severities[i % severities.length];
    return {
      type: "failed_action",
      defect: sev === "critical" ? "page_load_failure" : "missing_element",
      severity: sev,
      message: `Synthetic ${sev} defect #${i + 1}`,
      test_id: "deterministic_smoke",
    };
  });
}

export function seedScans(): ScanRecord[] {
  return urls.map((url, idx) => {
    const riskScore = 40 + (idx % 6) * 35;
    const riskLevel = riskScore > 200 ? "HIGH RISK" : riskScore > 100 ? "MEDIUM RISK" : "LOW RISK";
    const defects = 1 + (idx % 5);
    const issues = fakeIssues(defects);
    const project = DEMO_PROJECTS[idx % DEMO_PROJECTS.length];
    return toScanRecord({
      id: `scan_${idx + 1}`,
      url,
      date: new Date(Date.now() - (10 - idx) * 86400000).toISOString(),
      projectId: project.id,
      projectName: project.name,
      result: {
        summary: { total_pages_scanned: 1 + (idx % 4), total_actions_run: 4 + (idx % 3), total_issues_found: defects },
        risk_score: riskScore,
        risk_level: riskLevel,
        issues,
        issues_by_severity: {
          critical: issues.filter((i) => i.severity === "critical"),
          high: issues.filter((i) => i.severity === "high"),
          medium: issues.filter((i) => i.severity === "medium"),
          low: issues.filter((i) => i.severity === "low"),
        },
        pages: [{ url }],
        actions_run: [],
      },
    });
  });
}

