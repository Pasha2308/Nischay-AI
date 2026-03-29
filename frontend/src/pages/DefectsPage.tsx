import { loadScans } from "../store/scanStore";

export function DefectsPage() {
  const defects = loadScans().flatMap((s) => (s.result.issues ?? []).map((i) => ({ ...i, scanId: s.id, url: s.url })));
  if (defects.length === 0) {
    return (
      <div className="page">
        <h2>Defects</h2>
        <div className="card empty-state">
          <div className="issues-empty issues-empty--in-card">
            <p className="issues-empty-title">No issues found</p>
            <p className="issues-empty-sub">Your app looks healthy</p>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="page">
      <h2>Defects</h2>
      <div className="card">
        <ul className="issue-list">
          {defects.map((d, idx) => (
            <li key={`${idx}-${d.message}`} className={`issue ${d.severity ?? "medium"}`}>
              <span className={`badge ${d.severity ?? "medium"}`}>{d.severity ?? "medium"}</span>
              <div>{d.message}</div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

