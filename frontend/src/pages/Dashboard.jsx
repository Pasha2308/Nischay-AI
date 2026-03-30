import { motion } from "framer-motion";
import { Area, AreaChart, CartesianGrid, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Cell } from "recharts";
import { Activity, AlertTriangle, CheckCircle2, Shield } from "lucide-react";
import { MetricCard } from "../components/ui/MetricCard";
import { GlassCard } from "../components/ui/GlassCard";
import { SeverityBadge } from "../components/ui/SeverityBadge";
import { StatusDot } from "../components/ui/StatusDot";
import { useRuns } from "../hooks/useApi";

function riskColor(score) {
  const s = Number(score) || 0;
  if (s >= 81) return "var(--danger)";
  if (s >= 61) return "var(--high)";
  if (s >= 31) return "var(--warning)";
  return "var(--success)";
}

function fmtDate(d) {
  try {
    return new Date(d).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return String(d || "");
  }
}

function durToSeconds(dur) {
  if (!dur) return 0;
  const m = String(dur).match(/(\d+)\s*m/i);
  const s = String(dur).match(/(\d+)\s*s/i);
  return (m ? Number(m[1]) * 60 : 0) + (s ? Number(s[1]) : 0);
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass px-3 py-2 text-sm" style={{ border: "1px solid rgba(48,54,61,0.75)" }}>
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>{label}</div>
      <div className="font-mono font-semibold" style={{ color: "var(--accent-cyan)" }}>{payload[0].value}</div>
    </div>
  );
}

export function Dashboard() {
  const { runs, loading } = useRuns(true);
  const list = Array.isArray(runs) ? runs : [];

  const totalRuns = list.length;
  const avgRisk = totalRuns ? Math.round(list.reduce((n, r) => n + (Number(r.risk_score) || 0), 0) / totalRuns) : 0;
  const avgColor = riskColor(avgRisk);
  const avgLevel = avgRisk >= 81 ? "CRITICAL" : avgRisk >= 61 ? "HIGH" : avgRisk >= 31 ? "MEDIUM" : "LOW";

  const totalIssues = list.reduce((n, r) => n + (Number(r?.summary?.total_issues_found) || Number(r?.issues) || 0), 0);
  const totalTests = list.reduce((n, r) => n + (Number(r?.results?.total) || 0), 0);
  const passed = list.reduce((n, r) => n + (Number(r?.results?.passed) || 0), 0);
  const passRate = totalTests ? Math.round((passed / totalTests) * 100) : 0;

  const trend = list
    .slice()
    .reverse()
    .slice(-14)
    .map((r, i) => ({
      date: r.created_at ? fmtDate(r.created_at) : `#${i + 1}`,
      score: Number(r.risk_score) || 0,
    }));

  const severityAgg = list.reduce(
    (acc, r) => {
      const issues = r?.report?.issues || r?.results?.issues || r?.issues || [];
      const arr = Array.isArray(issues) ? issues : [];
      for (const it of arr) {
        const s = String(it.severity || it.level || "").toUpperCase();
        if (s.includes("CRITICAL")) acc.critical += 1;
        else if (s.includes("HIGH")) acc.high += 1;
        else if (s.includes("MEDIUM")) acc.medium += 1;
        else acc.low += 1;
      }
      return acc;
    },
    { critical: 0, high: 0, medium: 0, low: 0 },
  );

  const pieData = [
    { name: "Critical", value: severityAgg.critical, color: "var(--danger)" },
    { name: "High", value: severityAgg.high, color: "var(--high)" },
    { name: "Medium", value: severityAgg.medium, color: "var(--warning)" },
    { name: "Low", value: severityAgg.low, color: "var(--success)" },
  ];

  const recent = list.slice(0, 5);

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: "easeOut" }} className="grid gap-6 md:ml-[240px]">
      <div className="grid gap-4 md:grid-cols-4">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0 }}>
          <MetricCard title="Total Runs" value={totalRuns} subtitle="↑ 3 this week" icon={Activity} color="var(--accent-cyan)" />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <MetricCard
            title="Avg Risk Score"
            value={avgRisk}
            subtitle={<span className="inline-flex items-center gap-2"><SeverityBadge level={avgLevel} /></span>}
            icon={Shield}
            color={avgColor}
          />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
          <MetricCard title="Issues Found" value={totalIssues} subtitle="across all runs" icon={AlertTriangle} color="var(--warning)" />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
          <MetricCard
            title="Pass Rate"
            value={`${passRate}%`}
            subtitle={`${passed}/${totalTests || 0} passed`}
            icon={CheckCircle2}
            color="var(--success)"
            right={<MiniRing value={passRate} />}
          />
        </motion.div>
      </div>

      <div className="grid gap-4 md:grid-cols-5">
        <GlassCard className="p-5 md:col-span-3">
          <div className="flex items-center justify-between">
            <div className="font-display font-bold text-lg">Risk Score Trend</div>
            <div className="text-xs" style={{ color: "var(--text-secondary)" }}>{loading ? "Syncing…" : "Last runs"}</div>
          </div>
          <div className="mt-3 h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trend}>
                <defs>
                  <linearGradient id="cy" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent-cyan)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="var(--accent-cyan)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(33,38,45,0.9)" strokeDasharray="4 4" />
                <XAxis dataKey="date" tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                <YAxis tick={{ fill: "var(--text-muted)", fontSize: 11 }} domain={[0, 100]} />
                <Tooltip content={<CustomTooltip />} />
                <Area type="monotone" dataKey="score" stroke="var(--accent-cyan)" fill="url(#cy)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>

        <GlassCard className="p-5 md:col-span-2">
          <div className="flex items-center justify-between">
            <div className="font-display font-bold text-lg">Issues by Severity</div>
            <div className="text-xs" style={{ color: "var(--text-secondary)" }}>Total {totalIssues}</div>
          </div>
          <div className="mt-2 grid md:grid-cols-2 gap-3 items-center">
            <div className="h-[240px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={65} outerRadius={92} paddingAngle={2}>
                    {pieData.map((e) => (
                      <Cell key={e.name} fill={e.color} />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="grid gap-2">
              {pieData.map((e) => (
                <div key={e.name} className="flex items-center justify-between gap-3 text-sm">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ background: e.color }} />
                    <span className="truncate" style={{ color: "var(--text-secondary)" }}>{e.name}</span>
                  </div>
                  <span className="font-mono font-semibold" style={{ color: "var(--text-primary)" }}>{e.value}</span>
                </div>
              ))}
            </div>
          </div>
        </GlassCard>
      </div>

      <GlassCard className="p-5">
        <div className="flex items-center justify-between">
          <div className="font-display font-bold text-lg">Recent Runs</div>
          <a href="/history" className="text-sm font-semibold" style={{ color: "var(--accent-cyan)" }}>
            View All →
          </a>
        </div>
        <div className="mt-4 overflow-auto no-scrollbar">
          <table className="w-full text-sm" style={{ borderCollapse: "separate", borderSpacing: "0 10px" }}>
            <thead>
              <tr className="text-xs uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }}>
                <th className="text-left px-3">Run ID</th>
                <th className="text-left px-3">URL</th>
                <th className="text-left px-3">Date</th>
                <th className="text-left px-3">Duration</th>
                <th className="text-left px-3">Risk</th>
                <th className="text-left px-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((r) => {
                const id = r.run_id || r.id || "";
                const url = r.url || r.target_url || "";
                const date = r.created_at || r.date || "";
                const duration = r.duration || (r.start_time && r.end_time ? `${Math.max(0, Math.round((r.end_time - r.start_time) / 60))}m` : "—");
                const rs = Number(r.risk_score) || 0;
                const pill = riskColor(rs);
                return (
                  <tr
                    key={id}
                    className="hover:translate-y-[-1px]"
                    style={{ background: "rgba(15,17,23,0.75)", border: "1px solid rgba(48,54,61,0.65)" }}
                  >
                    <td className="px-3 py-3 font-mono font-semibold" style={{ color: "var(--accent-cyan)" }}>
                      {String(id).slice(0, 12)}
                    </td>
                    <td className="px-3 py-3 max-w-[420px] truncate" title={url} style={{ color: "var(--text-secondary)" }}>
                      {url}
                    </td>
                    <td className="px-3 py-3" style={{ color: "var(--text-secondary)" }}>
                      {fmtDate(date)}
                    </td>
                    <td className="px-3 py-3 font-mono" style={{ color: "var(--text-secondary)" }}>
                      {duration}
                    </td>
                    <td className="px-3 py-3">
                      <span className="px-2 py-1 rounded-lg font-mono font-semibold" style={{ background: "rgba(22,27,34,0.85)", color: pill, border: "1px solid rgba(48,54,61,0.65)" }}>
                        {rs}
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <StatusDot status={r.status || "completed"} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </motion.div>
  );
}

function MiniRing({ value = 0 }) {
  const v = Math.max(0, Math.min(100, Number(value) || 0));
  const r = 16;
  const c = 2 * Math.PI * r;
  const off = c * (1 - v / 100);
  return (
    <svg width="44" height="44" viewBox="0 0 44 44">
      <circle cx="22" cy="22" r={r} fill="none" stroke="rgba(48,54,61,0.9)" strokeWidth="6" />
      <circle
        cx="22"
        cy="22"
        r={r}
        fill="none"
        stroke="var(--success)"
        strokeWidth="6"
        strokeDasharray={c}
        strokeDashoffset={off}
        strokeLinecap="round"
        transform="rotate(-90 22 22)"
      />
    </svg>
  );
}

