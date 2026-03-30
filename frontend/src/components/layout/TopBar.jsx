import { useMemo, useState } from "react";
import { ChevronDown, Menu, Search, Bell } from "lucide-react";

function crumbForPath(path) {
  if (path === "/") return "Dashboard";
  const map = {
    "/new-test": "New Test",
    "/live": "Live Preview",
    "/modules": "Test Modules",
    "/results": "Results",
    "/history": "Run History",
    "/issues": "Issues Tracker",
    "/analytics": "Analytics",
    "/schedules": "Schedules",
    "/alerts": "Alerts",
    "/integrations": "Integrations",
    "/settings": "Settings",
  };
  return map[path] ?? "Nischay AI";
}

export function TopBar({ path, usingDemo }) {
  const [q, setQ] = useState("");
  const crumb = useMemo(() => crumbForPath(path), [path]);

  return (
    <header
      className="sticky top-0 z-20"
      style={{
        background: "rgba(10,12,16,0.72)",
        backdropFilter: "blur(14px)",
        borderBottom: "1px solid rgba(33,38,45,0.9)",
      }}
    >
      <div className="flex items-center gap-3 px-4 md:pl-[264px] md:pr-6 py-4">
        <button
          className="md:hidden h-10 w-10 rounded-xl grid place-items-center hover:bg-[rgba(48,54,61,0.35)]"
          aria-label="Open menu"
        >
          <Menu size={18} />
        </button>

        <div className="min-w-[160px]">
          <div className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
            Command Center
          </div>
          <div className="font-display text-lg font-bold" style={{ color: "var(--text-primary)" }}>
            {crumb}
          </div>
        </div>

        <div className="flex-1 min-w-0">
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--text-secondary)" }} />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search runs, issues, URLs..."
              className="w-full h-11 pl-10 pr-3 rounded-xl outline-none"
              style={{
                background: "rgba(15, 17, 23, 0.8)",
                border: "1px solid rgba(48, 54, 61, 0.75)",
                color: "var(--text-primary)",
              }}
            />
          </div>
        </div>

        <div className="flex items-center gap-2">
          {usingDemo ? (
            <div
              className="hidden sm:flex items-center gap-2 px-3 py-2 rounded-xl text-xs"
              style={{
                background: "rgba(245, 166, 35, 0.10)",
                border: "1px solid rgba(245, 166, 35, 0.35)",
                color: "var(--warning)",
              }}
              title="API unreachable — showing demo data"
            >
              Using demo data
            </div>
          ) : null}

          <button className="relative h-10 w-10 rounded-xl grid place-items-center hover:bg-[rgba(48,54,61,0.35)]" aria-label="Notifications">
            <Bell size={18} />
            <span className="absolute right-2 top-2 h-2 w-2 rounded-full" style={{ background: "var(--danger)" }} />
          </button>
          <button className="h-10 pl-2 pr-2 rounded-xl flex items-center gap-2 hover:bg-[rgba(48,54,61,0.35)]">
            <div
              className="h-8 w-8 rounded-full grid place-items-center font-semibold"
              style={{ background: "rgba(0,212,255,0.18)", border: "1px solid rgba(48,54,61,0.6)" }}
            >
              NA
            </div>
            <ChevronDown size={16} style={{ color: "var(--text-secondary)" }} />
          </button>
        </div>
      </div>
    </header>
  );
}

