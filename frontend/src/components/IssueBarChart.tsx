import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ScanResultPayload } from "../services/backend-service";

function countUiIssues(result: ScanResultPayload) {
  const issues = result.issues ?? [];
  return issues.filter((i) => {
    const m = (i.message ?? "").toLowerCase();
    const d = (i.defect ?? "").toLowerCase();
    return d.includes("ui") || m.includes("layout") || m.includes("render");
  }).length;
}

export function IssueBarChart({ result }: { result: ScanResultPayload }) {
  const data = [
    { name: "console errors", value: result.console_errors?.length ?? 0 },
    { name: "missing elements", value: result.missing_elements?.length ?? 0 },
    { name: "failed actions", value: result.failed_actions?.length ?? 0 },
    { name: "ui issues", value: countUiIssues(result) },
  ];

  return (
    <div className="card">
      <div className="card-title">Issue Categories</div>
      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 26 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="name" tick={{ fill: "#64748b", fontSize: 12 }} interval={0} angle={-12} textAnchor="end" />
            <YAxis tick={{ fill: "#64748b", fontSize: 12 }} allowDecimals={false} />
            <Tooltip />
            <Bar dataKey="value" fill="#2563eb" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

