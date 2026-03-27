import type { IssuesBySeverity } from "../services/backend-service";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

export function SeverityDonut({ buckets }: { buckets?: IssuesBySeverity }) {
  const c = buckets?.critical.length ?? 0;
  const h = buckets?.high.length ?? 0;
  const m = buckets?.medium.length ?? 0;
  const l = buckets?.low.length ?? 0;
  const data = [
    { name: "CRITICAL", value: c, color: "#dc2626" },
    { name: "HIGH", value: h, color: "#f97316" },
    { name: "MEDIUM", value: m, color: "#2563eb" },
    { name: "LOW", value: l, color: "#9ca3af" },
  ];

  return (
    <div className="donut-wrap">
      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height={240}>
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius={62} outerRadius={92} paddingAngle={2}>
              {data.map((entry) => (
                <Cell key={entry.name} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="legend">
        <span>Critical: {c}</span>
        <span>High: {h}</span>
        <span>Medium: {m}</span>
        <span>Low: {l}</span>
      </div>
    </div>
  );
}

