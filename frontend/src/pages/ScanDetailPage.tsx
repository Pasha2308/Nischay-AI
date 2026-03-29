import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { SeverityDonut } from "../components/SeverityDonut";
import { RiskGauge } from "../components/RiskGauge";
import { IssueBarChart } from "../components/IssueBarChart";
import { loadScans } from "../store/scanStore";
import { loadReqonSettings, pushScanToReqon } from "../services/reqon-integration";

export function ScanDetailPage() {
  const { id } = useParams();
  const scan = useMemo(() => loadScans().find((s) => s.id === id), [id]);
  const [pushing, setPushing] = useState(false);
  const [toast, setToast] = useState("");

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 2200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  if (!scan) return <div className="page">Scan not found.</div>;
  const issues = scan.result.issues ?? [];

  async function onPushToReqon() {
    setPushing(true);
    const settings = loadReqonSettings();
    const res = await pushScanToReqon(scan, settings);
    setToast(res.message);
    setPushing(false);
  }

  return (
    <div className="page">
      <h2>Scan Detail</h2>
      <div className="card executive-card">
        <div className="card-title">Executive Risk Summary</div>
        <p>
          {scan.result.executive_summary ??
            "Generating executive summary... Run again or refresh after a moment if this persists."}
        </p>
      </div>
      <div className="card">
        <div><strong>URL:</strong> {scan.url}</div>
        <div className="risk-hero">
          <div className="risk-hero-score">{scan.riskScore}</div>
          <span className={`badge ${scan.riskLevel === "HIGH RISK" ? "critical" : scan.riskLevel === "MEDIUM RISK" ? "high" : "low"}`}>
            {scan.riskLevel}
          </span>
        </div>
        <div className="toolbar">
          <button onClick={onPushToReqon} disabled={pushing}>
            {pushing ? "Pushing..." : "Push to ReQon"}
          </button>
          <span className="muted">Simulated integration call</span>
        </div>
      </div>
      <div className="detail-grid">
        <RiskGauge score={scan.riskScore} />
        <div className="card">
          <div className="card-title">Severity Breakdown</div>
          <SeverityDonut buckets={scan.result.issues_by_severity} />
        </div>
        <IssueBarChart result={scan.result} />
      </div>
      <div className="card">
        <div className="card-title">Defects</div>
        {issues.length === 0 ? (
          <div className="issues-empty">
            <p className="issues-empty-title">No issues found</p>
            <p className="issues-empty-sub">Your app looks healthy</p>
          </div>
        ) : (
          <ul className="issue-list">
            {issues.map((i, idx) => (
              <li key={`${idx}-${i.message}`} className={`issue ${i.severity ?? "medium"}`}>
                <span className={`badge ${i.severity ?? "medium"}`}>{i.severity ?? "medium"}</span>
                <span>{i.message}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {toast && <div className="toast success">{toast}</div>}
    </div>
  );
}

