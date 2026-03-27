import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Dashboard" },
  { to: "/projects", label: "Projects" },
  { to: "/history", label: "Scan History" },
  { to: "/defects", label: "Defects" },
  { to: "/synthetic", label: "Synthetic Data" },
  { to: "/settings", label: "Settings" },
];

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand-wrap">
        <div className="brand-mark" aria-hidden="true">
          RS
        </div>
        <div>
          <div className="brand">ReQon Scout</div>
          <div className="tagline">Autonomous QA. Zero setup.</div>
        </div>
      </div>
      <nav>
        {links.map((l) => (
          <NavLink key={l.to} to={l.to} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            {l.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}

