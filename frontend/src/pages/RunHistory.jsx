import { motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Eye, FileDown, RotateCcw, Search, Trash2, RefreshCw } from "lucide-react";
import { GlassCard } from "../components/ui/GlassCard";
import { StatusDot } from "../components/ui/StatusDot";
import { useNavigate } from "react-router-dom";
import { API, BASE_URL, INTERVALS } from "../config/api";

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

function normalizeRow(r) {
  const id = r.run_id ?? r.job_id ?? r.id ?? "";
  return {
    ...r,
    run_id: id,
    job_id: r.job_id ?? r.run_id ?? id,
    url: r.url ?? r.target_url ?? "",
    status: String(r.status ?? "").toLowerCase() || "completed",
    risk_score: Number(r.risk_score ?? r.riskScore ?? 0) || 0,
    created_at: r.created_at ?? r.started_at ?? r.date ?? "",
  };
}

export function RunHistory() {
  const nav = useNavigate();
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [tick, setTick] = useState(0);
  const [usingMock, setUsingMock] = useState(false);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");

  const fetchRuns = useCallback(async () => {
    try {
      const res = await fetch(API.getRuns);
      if (!res.ok) throw new Error("bad status");
      const data = await res.json();
      const raw = Array.isArray(data) ? data : data?.runs ?? [];
      setRuns(raw.map(normalizeRow));
      setUsingMock(false);
    } catch {
      setRuns([]);
      setUsingMock(true);
    } finally {
      setLoading(false);
      setLastUpdated(Date.now());
    }
  }, []);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  useEffect(() => {
    const t = window.setInterval(() => {
      fetchRuns();
    }, INTERVALS.historyRefresh);
    return () => window.clearInterval(t);
  }, [fetchRuns]);

  useEffect(() => {
    const t = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(t);
  }, []);

  const list = Array.isArray(runs) ? runs : [];

  const filtered = useMemo(() => {
    return list.filter((r) => {
      const url = String(r.url || "");
      const st = String(r.status || "");
      if (q && !url.toLowerCase().includes(q.toLowerCase())) return false;
      if (status !== "all" && st !== status) return false;
      return true;
    });
  }, [list, q, status]);

  const secondsAgo = useMemo(() => {
    if (lastUpdated == null) return null;
    return Math.max(0, Math.floor((Date.now() - lastUpdated) / 1000));
  }, [lastUpdated, tick]);

  async function onRerun(e, row) {
    e.stopPropagation();
    const id = row.run_id || row.job_id || row.id;
    if (!id) return;
    try {
      const res = await fetch(API.rerun(id), { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      if (!res.ok) throw new Error("rerun failed");
      const data = await res.json();
      const newId = data.run_id ?? data.job_id ?? data.id;
      if (newId) nav(`/live/${encodeURIComponent(newId)}`);
    } catch {
      /* noop — backend may not support */
    }
  }

  function exportCsv() {
    const rows = filtered.map((r) => ({
      run_id: r.run_id || r.job_id || "",
      url: r.url || "",
      status: r.status || "",
      risk_score: r.risk_score ?? "",
      created_at: r.created_at || "",
    }));
    const headers = Object.keys(rows[0] || { run_id: "", url: "", status: "", risk_score: "", created_at: "" });
    const esc = (v) => `"${String(v ?? "").split('"').join('""')}"`;
    const body = rows.map((rr) => headers.map((h) => esc(rr[h])).join(","));
    const csv = [headers.join(","), ...body].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "nischay_runs.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: "easeOut" }} className="grid gap-6 md:ml-[240px]">
      {usingMock ? (
        <div
          style={{
            background: "rgba(245,166,35,0.08)",
            border: "1px solid rgba(245,166,35,0.3)",
            borderRadius: "8px",
            padding: "10px 16px",
          }}
        >
          <span style={{ color: "#F5A623", fontSize: "13px" }}>⚠ Could not load run history — check backend at {BASE_URL}</span>
        </div>
      ) : null}

      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="font-display text-2xl font-extrabold">Run History</div>
          <div className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
            {secondsAgo !== null ? `Updated ${secondsAgo}s ago` : loading ? "Loading…" : ""}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => fetchRuns()}
            className="h-11 px-4 rounded-xl font-semibold inline-flex items-center gap-2"
            style={{ background: "rgba(22,27,34,0.75)", color: "var(--text-secondary)", border: "1px solid rgba(48,54,61,0.7)" }}
          >
            <RefreshCw size={16} />
            Refresh
          </button>
          <button
            type="button"
            onClick={exportCsv}
            className="h-11 px-4 rounded-xl font-semibold inline-flex items-center gap-2"
            style={{ background: "rgba(22,27,34,0.75)", color: "var(--text-secondary)", border: "1px solid rgba(48,54,61,0.7)" }}
          >
            <FileDown size={16} />
            Export CSV
          </button>
        </div>
      </div>

      <GlassCard className="p-4 flex flex-col md:flex-row gap-3 md:items-center">
        <div className="relative flex-1 min-w-0">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--text-secondary)" }} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter by URL…"
            className="w-full h-11 pl-10 pr-3 rounded-xl outline-none"
            style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }}
          />
        </div>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="h-11 rounded-xl px-3 outline-none"
          style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-primary)" }}
        >
          <option value="all">All statuses</option>
          <option value="running">running</option>
          <option value="completed">completed</option>
          <option value="failed">failed</option>
        </select>
      </GlassCard>

      <GlassCard className="p-5">
        <div className="overflow-auto no-scrollbar">
          <table className="w-full text-sm" style={{ borderCollapse: "separate", borderSpacing: "0 10px" }}>
            <thead>
              <tr className="text-xs uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }}>
                <th className="text-left px-3">#</th>
                <th className="text-left px-3">Run ID</th>
                <th className="text-left px-3">URL</th>
                <th className="text-left px-3">Date</th>
                <th className="text-left px-3">Risk</th>
                <th className="text-left px-3">Status</th>
                <th className="text-left px-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r, idx) => {
                const id = r.run_id || r.job_id || r.id || "";
                const url = r.url || r.target_url || "";
                const date = r.created_at || r.started_at || r.date || "";
                const score = Number(r.risk_score) || 0;
                const c = riskColor(score);
                return (
                  <tr key={id || idx} style={{ background: "rgba(15,17,23,0.75)", border: "1px solid rgba(48,54,61,0.65)" }}>
                    <td className="px-3 py-3 font-mono" style={{ color: "var(--text-muted)" }}>
                      {idx + 1}
                    </td>
                    <td
                      className="px-3 py-3 font-mono font-semibold cursor-pointer"
                      style={{ color: "var(--accent-cyan)" }}
                      onClick={() => {
                        navigator.clipboard?.writeText(String(id));
                      }}
                      title="Copy run id"
                    >
                      {String(id).slice(0, 12)}
                    </td>
                    <td className="px-3 py-3 max-w-[520px] truncate" title={url} style={{ color: "var(--text-secondary)" }}>
                      {url}
                    </td>
                    <td className="px-3 py-3" style={{ color: "var(--text-secondary)" }}>
                      {fmtDate(date)}
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-1 rounded-lg font-mono font-semibold" style={{ background: "rgba(22,27,34,0.85)", color: c, border: "1px solid rgba(48,54,61,0.65)" }}>
                          {score}
                        </span>
                        <div className="h-2 w-20 rounded-full" style={{ background: "rgba(48,54,61,0.55)" }}>
                          <div className="h-2 rounded-full" style={{ width: `${Math.min(100, score)}%`, background: c }} />
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <StatusDot status={r.status || "completed"} />
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => nav(`/results/${encodeURIComponent(id)}`)}
                          className="h-9 w-9 rounded-xl grid place-items-center hover:scale-[1.03]"
                          style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}
                          aria-label="View"
                        >
                          <Eye size={16} />
                        </button>
                        <button
                          type="button"
                          onClick={(e) => onRerun(e, r)}
                          className="h-9 w-9 rounded-xl grid place-items-center hover:scale-[1.03]"
                          style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}
                          aria-label="Rerun"
                        >
                          <RotateCcw size={16} />
                        </button>
                        <button
                          type="button"
                          className="h-9 w-9 rounded-xl grid place-items-center hover:scale-[1.03]"
                          style={{ background: "rgba(255,68,68,0.10)", border: "1px solid rgba(255,68,68,0.25)", color: "var(--danger)" }}
                          aria-label="Delete"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {!filtered.length && !loading ? (
                <tr>
                  <td colSpan={7}>
                    <div className="glass p-8 text-center">
                      <div className="font-display text-xl font-bold">No test runs yet</div>
                      <div className="text-sm mt-2" style={{ color: "var(--text-secondary)" }}>
                        Run your first QA test to see history.
                      </div>
                      <a
                        href="/new-test"
                        className="inline-flex mt-4 h-11 px-4 rounded-xl font-semibold items-center"
                        style={{ background: "linear-gradient(135deg, #00D4FF, #7C3AED)", color: "#0A0C10" }}
                      >
                        Run Test
                      </a>
                    </div>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </motion.div>
  );
}
