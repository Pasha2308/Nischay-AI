import { NavLink } from "react-router-dom";
import {
  Bell,
  Bug,
  CalendarClock,
  Clock,
  HelpCircle,
  Layers,
  LayoutDashboard,
  Monitor,
  Play,
  Plug,
  Settings,
  TrendingUp,
} from "lucide-react";
import { useBackendHealth } from "../../hooks/useBackendHealth";

function Brand() {
  return (
    <div className="flex items-center gap-3 px-4 py-5">
      <img
        src="/logo.png"
        alt="Nischay AI"
        className="h-8 w-auto object-contain"
        onError={(e) => {
          e.target.style.display = "none";
          e.target.nextSibling.style.display = "flex";
        }}
      />
      <div style={{ display: "none" }} className="flex items-center gap-2">
        <svg viewBox="0 0 40 40" className="h-8 w-8" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M20 3L35 12V28L20 37L5 28V12L20 3Z" stroke="url(#grad)" strokeWidth="2" fill="none" />
          <path d="M20 10L15 22H19L18 30L25 18H21L23 10H20Z" fill="#00D4FF" />
          <defs>
            <linearGradient id="grad" x1="5" y1="3" x2="35" y2="37">
              <stop offset="0%" stopColor="#00D4FF" />
              <stop offset="100%" stopColor="#7C3AED" />
            </linearGradient>
          </defs>
        </svg>
        <span
          style={{
            fontFamily: "Syne,sans-serif",
            fontWeight: 700,
            color: "#E6EDF3",
            fontSize: "18px",
          }}
        >
          Nischay<span style={{ color: "#00D4FF" }}>AI</span>
        </span>
      </div>
      <span
        className="logo-text"
        style={{
          fontFamily: "Syne,sans-serif",
          fontWeight: 700,
          color: "#E6EDF3",
          fontSize: "18px",
        }}
      >
        Nischay<span style={{ color: "#00D4FF" }}>AI</span>
      </span>
    </div>
  );
}

function Section({ label }) {
  return (
    <div className="px-4 pt-5 pb-2 text-[11px] tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
      {label}
    </div>
  );
}

function Item({ to, icon: Icon, label }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        [
          "group mx-3 my-1 flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm",
          isActive ? "bg-[rgba(0,212,255,0.08)]" : "hover:bg-[rgba(48,54,61,0.35)]",
        ].join(" ")
      }
      style={({ isActive }) => ({
        color: isActive ? "var(--accent-cyan)" : "var(--text-secondary)",
        borderLeft: isActive ? "3px solid var(--accent-cyan)" : "3px solid transparent",
      })}
    >
      <Icon size={18} className="opacity-90 group-hover:opacity-100" />
      <span className="truncate">{label}</span>
    </NavLink>
  );
}

export function Sidebar() {
  const { isOnline, version } = useBackendHealth();

  return (
    <aside
      className="hidden md:flex md:flex-col md:w-[240px] md:fixed md:inset-y-0 md:left-0 md:z-30"
      style={{ background: "rgba(15, 17, 23, 0.75)", borderRight: "1px solid rgba(33,38,45,0.9)" }}
    >
      <Brand />
      <div className="flex-1 overflow-auto no-scrollbar pb-4">
        <Section label="MAIN" />
        <Item to="/" icon={LayoutDashboard} label="Dashboard" />

        <Section label="TESTING" />
        <Item to="/new-test" icon={Play} label="New Test" />
        <Item to="/live" icon={Monitor} label="Live Preview" />
        <Item to="/modules" icon={Layers} label="Test Modules" />

        <Section label="RESULTS" />
        <Item to="/history" icon={Clock} label="Run History" />
        <Item to="/issues" icon={Bug} label="Issues Tracker" />

        <Section label="MONITORING" />
        <Item to="/analytics" icon={TrendingUp} label="Analytics" />
        <Item to="/schedules" icon={CalendarClock} label="Schedules" />
        <Item to="/alerts" icon={Bell} label="Alerts" />

        <Section label="SYSTEM" />
        <Item to="/integrations" icon={Plug} label="Integrations" />
        <Item to="/settings" icon={Settings} label="Settings" />
      </div>

      <div style={{ padding: "12px 16px", borderTop: "1px solid #21262D", display: "flex", alignItems: "center", gap: "8px" }}>
        <div
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: isOnline === null ? "#484F58" : isOnline ? "#00C896" : "#FF4444",
            animation: isOnline ? "pulse 2s ease-in-out infinite" : "none",
            flexShrink: 0,
          }}
        />
        <span
          style={{
            fontFamily: "DM Sans,sans-serif",
            fontSize: "12px",
            color: isOnline === null ? "#484F58" : isOnline ? "#00C896" : "#FF4444",
          }}
        >
          {isOnline === null
            ? "Checking backend..."
            : isOnline
              ? `Backend Online${version ? ` v${version}` : ""}`
              : "Backend Offline — Demo Mode"}
        </span>
      </div>

      <div className="px-3 py-3" style={{ borderTop: "1px solid rgba(33,38,45,0.9)" }}>
        <div className="flex items-center justify-between rounded-xl px-3 py-2.5 hover:bg-[rgba(48,54,61,0.35)]">
          <div className="flex items-center gap-3 min-w-0">
            <div
              className="h-8 w-8 rounded-full grid place-items-center font-semibold"
              style={{ background: "rgba(0,212,255,0.18)", color: "var(--text-primary)", border: "1px solid rgba(48,54,61,0.6)" }}
            >
              NA
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold truncate" style={{ color: "var(--text-primary)" }}>
                Nischay Analyst
              </div>
              <div className="text-xs truncate" style={{ color: "var(--text-secondary)" }}>
                QA Operations
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <NavLink to="/settings" className="p-2 rounded-lg hover:bg-[rgba(48,54,61,0.45)]" aria-label="Settings">
              <Settings size={18} />
            </NavLink>
            <NavLink to="/help" className="p-2 rounded-lg hover:bg-[rgba(48,54,61,0.45)]" aria-label="Help">
              <HelpCircle size={18} />
            </NavLink>
          </div>
        </div>
      </div>
    </aside>
  );
}
