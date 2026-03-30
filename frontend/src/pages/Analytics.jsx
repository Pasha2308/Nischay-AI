import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { GlassCard } from "../components/ui/GlassCard";
import { useRuns } from "../hooks/useApi";

function toPoints(runs) {
  return runs
    .slice()
    .reverse()
    .map((r, i) => ({
      date: r.created_at ? new Date(r.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : `#${i + 1}`,
      score: Number(r.risk_score) || 0,
      issues: Number(r?.summary?.total_issues_found) || 0,
      passed: Number(r?.results?.passed) || 0,
      total: Number(r?.results?.total) || 0,
    }));
}

function tooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass px-3 py-2 text-sm" style={{ border: "1px solid rgba(48,54,61,0.75)" }}>
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="font-mono" style={{ color: "var(--text-primary)" }}>
          {p.dataKey}: <span style={{ color: "var(--accent-cyan)" }}>{p.value}</span>
        </div>
      ))}
    </div>
  );
}

export function Analytics() {
  const { runs } = useRuns(true);
  const [range, setRange] = useState("7d");
  const list = Array.isArray(runs) ? runs : [];

  const points = useMemo(() => {
    const p = toPoints(list);
    if (range === "7d") return p.slice(-7);
    if (range === "30d") return p.slice(-30);
    if (range === "90d") return p.slice(-90);
    return p;
  }, [list, range]);

  const passTrend = useMemo(() => points.map((p) => ({ date: p.date, passRate: p.total ? Math.round((p.passed / p.total) * 100) : 0 })), [points]);

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: "easeOut" }} className="grid gap-6 md:ml-[240px]">
      <div className="flex items-center justify-between gap-3">
        <div className="font-display text-2xl font-extrabold">Analytics</div>
        <div className="flex gap-2">
          {[
            ["7d", "Last 7d"],
            ["30d", "30d"],
            ["90d", "90d"],
            ["all", "All Time"],
          ].map(([k, label]) => (
            <button
              key={k}
              type="button"
              onClick={() => setRange(k)}
              className="h-10 px-3 rounded-xl text-sm font-semibold"
              style={{
                background: range === k ? "rgba(0,212,255,0.14)" : "rgba(22,27,34,0.75)",
                color: range === k ? "var(--accent-cyan)" : "var(--text-secondary)",
                border: "1px solid rgba(48,54,61,0.7)",
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-5">
        <GlassCard className="p-5 md:col-span-3">
          <div className="font-display font-bold text-lg">Risk Score Over Time</div>
          <div className="mt-3 h-[320px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={points}>
                <defs>
                  <linearGradient id="riskA" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent-cyan)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="var(--accent-cyan)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(33,38,45,0.9)" strokeDasharray="4 4" />
                <XAxis dataKey="date" tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                <Tooltip content={tooltip} />
                <Area type="monotone" dataKey="score" stroke="var(--accent-cyan)" fill="url(#riskA)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>

        <GlassCard className="p-5 md:col-span-2">
          <div className="font-display font-bold text-lg">Issue Types Distribution</div>
          <div className="mt-3 h-[320px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={points}>
                <CartesianGrid stroke="rgba(33,38,45,0.9)" strokeDasharray="4 4" />
                <XAxis dataKey="date" tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                <YAxis tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                <Tooltip content={tooltip} />
                <Bar dataKey="issues" fill="var(--warning)" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <GlassCard className="p-5">
          <div className="font-display font-bold text-lg">Test Pass Rate Trend</div>
          <div className="mt-3 h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={passTrend}>
                <defs>
                  <linearGradient id="passA" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--success)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="var(--success)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(33,38,45,0.9)" strokeDasharray="4 4" />
                <XAxis dataKey="date" tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                <Tooltip content={tooltip} />
                <Area type="monotone" dataKey="passRate" stroke="var(--success)" fill="url(#passA)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>
        <GlassCard className="p-5">
          <div className="font-display font-bold text-lg">Most Tested URLs</div>
          <div className="mt-3 text-sm" style={{ color: "var(--text-secondary)" }}>
            URL aggregation requires an API issues endpoint; demo view summarizes run target URLs instead.
          </div>
          <div className="mt-4 grid gap-2">
            {list.slice(0, 6).map((r) => (
              <div key={r.run_id} className="flex items-center justify-between gap-3 glass px-3 py-2">
                <div className="truncate font-mono text-xs" style={{ color: "var(--text-secondary)" }}>
                  {r.url || r.target_url}
                </div>
                <div className="font-mono text-xs" style={{ color: "var(--accent-cyan)" }}>
                  {Number(r.risk_score) || 0}
                </div>
              </div>
            ))}
          </div>
        </GlassCard>
      </div>
    </motion.div>
  );
}

