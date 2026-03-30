import { motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, LabelList } from "recharts";
import { GlassCard } from "../components/ui/GlassCard";

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
  const [range, setRange] = useState("7d");
  const [summary, setSummary] = useState(null);
  const [riskTrend, setRiskTrend] = useState([]);
  const [issueDist, setIssueDist] = useState([]);
  const [passRate, setPassRate] = useState([]);
  const [topUrls, setTopUrls] = useState([]);

  const baseUrl = useMemo(() => {
    if (typeof window !== "undefined" && window.location && window.location.hostname) {
      const h = window.location.hostname;
      if (h === "localhost" || h === "127.0.0.1") return "http://localhost:8000";
    }
    return "https://api.nischay.ai";
  }, []);

  const days = range === "7d" ? 7 : range === "30d" ? 30 : range === "90d" ? 90 : 365;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await fetch(`${baseUrl}/analytics/summary`).then((r) => r.json());
        const rt = await fetch(`${baseUrl}/analytics/risk-trend?days=${days}`).then((r) => r.json());
        const id = await fetch(`${baseUrl}/analytics/issue-distribution?days=${days}`).then((r) => r.json());
        const pr = await fetch(`${baseUrl}/analytics/pass-rate?days=${days}`).then((r) => r.json());
        const tu = await fetch(`${baseUrl}/analytics/top-urls?days=${days}&limit=10`).then((r) => r.json());
        if (cancelled) return;
        setSummary(s && typeof s === "object" ? s : null);
        setRiskTrend(Array.isArray(rt) ? rt : []);
        setIssueDist(Array.isArray(id) ? id : []);
        setPassRate(Array.isArray(pr) ? pr : []);
        setTopUrls(Array.isArray(tu) ? tu : []);
      } catch {
        if (cancelled) return;
        setSummary(null);
        setRiskTrend([]);
        setIssueDist([]);
        setPassRate([]);
        setTopUrls([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [baseUrl, days]);

  const riskPoints = useMemo(
    () =>
      (Array.isArray(riskTrend) ? riskTrend : []).map((r) => ({
        date: r.date,
        dateLabel: new Date(r.date).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
        avg_risk_score: Number(r.avg_risk_score) || 0,
        scan_count: Number(r.scan_count) || 0,
      })),
    [riskTrend],
  );

  const passPoints = useMemo(
    () =>
      (Array.isArray(passRate) ? passRate : []).map((r) => ({
        date: r.date,
        dateLabel: new Date(r.date).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
        pass_rate: Number(r.pass_rate) || 0,
        total_runs: Number(r.total_runs) || 0,
      })),
    [passRate],
  );

  const issuePoints = useMemo(
    () =>
      (Array.isArray(issueDist) ? issueDist : []).map((r) => ({
        type: r.type,
        label: r.label,
        count: Number(r.count) || 0,
        severity: r.severity,
        fill:
          r.severity === "critical"
            ? "#ef4444"
            : r.severity === "high"
            ? "#f97316"
            : r.severity === "medium"
            ? "#eab308"
            : "#3b82f6",
      })),
    [issueDist],
  );

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

      <div className="grid gap-4 md:grid-cols-4">
        <KpiCard label="Total Scans" value={summary?.total_scans ?? "—"} />
        <KpiCard label="Avg Risk" value={summary?.avg_risk_score ?? "—"} />
        <KpiCard label="Open Critical" value={summary?.critical_issues_open ?? "—"} />
        <KpiCard label="Resolved This Week" value={summary?.issues_resolved_this_week ?? "—"} />
      </div>

      <div className="grid gap-4 md:grid-cols-5">
        <GlassCard className="p-5 md:col-span-3">
          <div className="font-display font-bold text-lg">Risk Score Over Time</div>
          <div className="mt-3 h-[320px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={riskPoints}>
                <defs>
                  <linearGradient id="riskA" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent-cyan)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="var(--accent-cyan)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(33,38,45,0.9)" strokeDasharray="4 4" />
                <XAxis dataKey="dateLabel" tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const p = payload[0]?.payload;
                    return (
                      <div className="glass px-3 py-2 text-sm" style={{ border: "1px solid rgba(48,54,61,0.75)" }}>
                        <div className="text-xs" style={{ color: "var(--text-muted)" }}>{p.dateLabel}</div>
                        <div className="font-mono" style={{ color: "var(--text-primary)" }}>
                          Avg risk: <span style={{ color: "var(--accent-cyan)" }}>{p.avg_risk_score}</span>
                        </div>
                        <div className="font-mono" style={{ color: "var(--text-primary)" }}>
                          Scans: <span style={{ color: "var(--accent-cyan)" }}>{p.scan_count}</span>
                        </div>
                      </div>
                    );
                  }}
                />
                <ReferenceLine y={70} stroke="#ef4444" strokeDasharray="6 6" label={{ value: "Alert threshold", fill: "#ef4444", fontSize: 11, position: "insideTopRight" }} />
                <Area type="monotone" dataKey="avg_risk_score" stroke="var(--accent-cyan)" fill="url(#riskA)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>

        <GlassCard className="p-5 md:col-span-2">
          <div className="font-display font-bold text-lg">Issue Types (last {days} days)</div>
          <div className="mt-3 h-[320px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={issuePoints} layout="vertical" margin={{ left: 40, right: 20 }}>
                <CartesianGrid stroke="rgba(33,38,45,0.9)" strokeDasharray="4 4" />
                <XAxis type="number" tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                <YAxis type="category" dataKey="label" tick={{ fill: "var(--text-muted)", fontSize: 11 }} width={120} />
                <Tooltip content={tooltip} />
                <Bar dataKey="count" radius={[8, 8, 8, 8]}>
                  <LabelList dataKey="count" position="right" fill="var(--text-secondary)" fontSize={11} />
                  {issuePoints.map((e) => (
                    <Cell key={e.type} fill={e.fill} />
                  ))}
                </Bar>
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
              <LineChart data={passPoints}>
                <CartesianGrid stroke="rgba(33,38,45,0.9)" strokeDasharray="4 4" />
                <XAxis dataKey="dateLabel" tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fill: "var(--text-muted)", fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                <Tooltip content={tooltip} />
                <ReferenceLine y={80} stroke="var(--success)" strokeDasharray="6 6" label={{ value: "Target", fill: "var(--success)", fontSize: 11, position: "insideTopRight" }} />
                <Line type="monotone" dataKey="pass_rate" stroke="var(--success)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>
        <GlassCard className="p-5">
          <div className="font-display font-bold text-lg">Most Tested URLs</div>
          <div className="mt-4 grid gap-2">
            {topUrls.map((r) => (
              <button
                key={r.url}
                type="button"
                onClick={() => {
                  if (r.last_report_id) window.open(`${baseUrl}/report/${r.last_report_id}`, "_blank");
                }}
                className="flex items-center justify-between gap-3 glass px-3 py-2 text-left"
              >
                <div className="truncate font-mono text-xs" style={{ color: "var(--text-secondary)" }} title={r.url}>
                  {r.url}
                </div>
                <div className="flex items-center gap-2">
                  <span className="px-2 py-1 rounded-full text-xs font-semibold" style={{ background: "rgba(48,54,61,0.55)", color: "var(--text-secondary)" }}>
                    {r.scan_count}
                  </span>
                  <span className="font-mono text-xs" style={{ color: Number(r.avg_risk_score) >= 70 ? "#ef4444" : "var(--accent-cyan)" }}>
                    {r.avg_risk_score}
                  </span>
                  <span className="text-xs" style={{ color: r.trend === "improving" ? "var(--success)" : r.trend === "worsening" ? "#ef4444" : "var(--text-muted)" }}>
                    {r.trend === "improving" ? "↓" : r.trend === "worsening" ? "↑" : "→"}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </GlassCard>
      </div>
    </motion.div>
  );
}

function KpiCard({ label, value }) {
  return (
    <GlassCard className="p-5">
      <div className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
        {label}
      </div>
      <div className="mt-2 font-display text-3xl font-extrabold" style={{ color: "var(--text-primary)" }}>
        {value}
      </div>
    </GlassCard>
  );
}

