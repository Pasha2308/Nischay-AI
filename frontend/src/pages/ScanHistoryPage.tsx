import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { loadScans } from "../store/scanStore";

export function ScanHistoryPage() {
  const navigate = useNavigate();
  const scans = useMemo(() => loadScans(), []);
  if (scans.length === 0) {
    return (
      <div className="page">
        <h2>Scan History</h2>
        <div className="card empty-state">
          <p>No scans yet. Start your first scan from the Dashboard.</p>
        </div>
      </div>
    );
  }
  return (
    <div className="page">
      <h2>Scan History</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>URL</th><th>Date</th><th>Status</th><th>Risk Score</th><th>Defect Count</th>
            </tr>
          </thead>
          <tbody>
            {scans.map((s) => (
              <tr key={s.id} className="clickable" onClick={() => navigate(`/scans/${s.id}`)}>
                <td>{s.url}</td>
                <td>{new Date(s.date).toLocaleString()}</td>
                <td>{s.status}</td>
                <td>{s.riskScore}</td>
                <td>{s.defectCount}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

