type Point = { xLabel: string; y: number };
import { CartesianGrid, Line, LineChart as RLineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function LineChart({ points, title }: { points: Point[]; title: string }) {
  const data = points.map((p) => ({ name: p.xLabel, risk: p.y }));

  return (
    <div className="card">
      <div className="card-title">{title}</div>
      {data.length === 0 && <p className="muted">No scan trend yet. Run your first scan.</p>}
      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height={260}>
          <RLineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="name" tick={{ fill: "#64748b", fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#64748b", fontSize: 12 }} axisLine={false} tickLine={false} />
            <Tooltip />
            <Line type="monotone" dataKey="risk" stroke="#2563eb" strokeWidth={3} dot={{ r: 3 }} />
          </RLineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

