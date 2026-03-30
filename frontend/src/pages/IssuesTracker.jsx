import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import { Bug } from "lucide-react";
import { GlassCard } from "../components/ui/GlassCard";
import { SeverityBadge } from "../components/ui/SeverityBadge";
import { EmptyState } from "../components/ui/EmptyState";
import { mockIssues } from "../data/mockData";

function colFor(status) {
  const s = String(status || "").toLowerCase();
  if (s === "resolved") return "RESOLVED";
  if (s === "ignored") return "IGNORED";
  return "OPEN";
}

export function IssuesTracker() {
  const [q, setQ] = useState("");
  const [sev, setSev] = useState("all");
  const issues = mockIssues;

  const filtered = useMemo(() => {
    return issues.filter((i) => {
      if (q && !String(i.description).toLowerCase().includes(q.toLowerCase())) return false;
      if (sev !== "all" && String(i.severity).toUpperCase() !== sev) return false;
      return true;
    });
  }, [issues, q, sev]);

  const cols = useMemo(() => {
    const m = { OPEN: [], RESOLVED: [], IGNORED: [] };
    for (const i of filtered) m[colFor(i.status)].push(i);
    return m;
  }, [filtered]);

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: "easeOut" }} className="grid gap-6 md:ml-[240px]">
      <div className="flex items-center justify-between gap-3">
        <div className="font-display text-2xl font-extrabold">Issues Tracker</div>
        <div className="flex items-center gap-2">
          <select
            value={sev}
            onChange={(e) => setSev(e.target.value)}
            className="h-11 rounded-xl px-3 outline-none"
            style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-primary)" }}
          >
            <option value="all">All severities</option>
            <option value="CRITICAL">Critical</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search issues…"
            className="h-11 rounded-xl px-3 outline-none w-[260px]"
            style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }}
          />
        </div>
      </div>

      {!filtered.length ? (
        <EmptyState icon={Bug} title="No issues matched" subtitle="Adjust filters to view issues across runs." actionLabel="Reset filters" onAction={() => { setQ(""); setSev("all"); }} />
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          <Column title="OPEN" color="var(--danger)" items={cols.OPEN} />
          <Column title="RESOLVED" color="var(--success)" items={cols.RESOLVED} />
          <Column title="IGNORED" color="var(--text-muted)" items={cols.IGNORED} />
        </div>
      )}
    </motion.div>
  );
}

function Column({ title, color, items }) {
  return (
    <GlassCard className="p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
          <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
            {title}
          </div>
        </div>
        <div className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
          {items.length}
        </div>
      </div>
      <div className="mt-3 grid gap-3">
        {items.map((i) => (
          <div key={i.id} className="glass p-4 hover:translate-y-[-1px]">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm font-semibold truncate">{i.type}</div>
                <div className="text-xs font-mono truncate mt-1" style={{ color: "var(--text-secondary)" }}>
                  {i.url}
                </div>
              </div>
              <SeverityBadge level={i.severity} />
            </div>
            <div className="mt-3 text-sm" style={{ color: "var(--text-secondary)" }}>
              {i.description}
            </div>
            <div className="mt-3 flex items-center justify-between text-xs" style={{ color: "var(--text-muted)" }}>
              <span>First seen {i.firstSeen}</span>
              <span className="px-2 py-1 rounded-full" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }}>
                {i.runCount} runs
              </span>
            </div>
          </div>
        ))}
      </div>
    </GlassCard>
  );
}

