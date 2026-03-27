import type { ScanRecord } from "../types";

export function ActivityFeed({ scans }: { scans: ScanRecord[] }) {
  return (
    <div className="card">
      <div className="card-title">Recent Activity</div>
      {scans.length === 0 && <p className="muted">No recent activity yet.</p>}
      <ul className="feed">
        {scans.slice(0, 6).map((s) => (
          <li key={s.id}>
            <div>{s.url}</div>
            <small>{new Date(s.date).toLocaleString()} · {s.riskLevel}</small>
          </li>
        ))}
      </ul>
    </div>
  );
}

