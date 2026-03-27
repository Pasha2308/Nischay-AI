import { DEMO_PROJECTS } from "../data/seed";
import { loadScans } from "../store/scanStore";

export function ProjectsPage() {
  const scans = loadScans();
  if (scans.length === 0) {
    return (
      <div className="page">
        <h2>Projects</h2>
        <div className="card empty-state">
          <p>No project analytics yet. Add scans to populate this view.</p>
        </div>
      </div>
    );
  }
  return (
    <div className="page">
      <h2>Projects</h2>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Project</th><th>Scans</th><th>Avg Risk</th></tr></thead>
          <tbody>
            {DEMO_PROJECTS.map((p) => {
              const list = scans.filter((s) => s.projectId === p.id);
              const avg = list.length ? Math.round(list.reduce((n, s) => n + s.riskScore, 0) / list.length) : 0;
              return <tr key={p.id}><td>{p.name}</td><td>{list.length}</td><td>{avg}</td></tr>;
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

