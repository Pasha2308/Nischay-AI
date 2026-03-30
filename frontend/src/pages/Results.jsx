import { motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertCircle, FileSearch, MousePointer, Timer, ChevronDown } from "lucide-react";
import { GlassCard } from "../components/ui/GlassCard";
import { SeverityBadge } from "../components/ui/SeverityBadge";
import { LoadingSkeleton } from "../components/ui/LoadingSkeleton";
import { API, BASE_URL, INTERVALS } from "../config/api";
import { mockRuns, mockIssues } from "../data/mockData";

function evidenceFullUrl(path) {
  if (!path) return "";
  const p = String(path);
  if (p.startsWith("http")) return p;
  return `${BASE_URL}${p.startsWith("/") ? p : `/${p}`}`;
}

function uxColorForScore(ux) {
  const s = Math.max(0, Math.min(100, Number(ux) || 0));
  if (s >= 81) return "var(--success)";
  if (s >= 61) return "var(--accent-cyan)";
  if (s >= 31) return "var(--warning)";
  return "var(--danger)";
}

function UXScoreGauge({ uxScore = 0, uxLabel = "" }) {
  const s = Math.max(0, Math.min(100, Number(uxScore) || 0));
  const c = useMemo(() => uxColorForScore(s), [s]);
  const r = 80;
  const cx = 100;
  const cy = 100;
  const startAngle = 180;
  const endAngle = 0;
  const [anim, setAnim] = useState(0);
  const [num, setNum] = useState(0);

  useEffect(() => {
    setAnim(0);
    setNum(0);
    const t0 = performance.now();
    const dur = 1200;
    let raf = 0;
    function tick(now) {
      const p = Math.min(1, (now - t0) / dur);
      const ease = 1 - Math.pow(1 - p, 3);
      setAnim(ease);
      setNum(Math.round(s * ease));
      if (p < 1) raf = requestAnimationFrame(tick);
    }
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [s]);

  function polarToCartesian(angleDeg) {
    const a = ((angleDeg - 90) * Math.PI) / 180.0;
    return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  }

  function arcPath(a0, a1) {
    const p0 = polarToCartesian(a1);
    const p1 = polarToCartesian(a0);
    const largeArc = a1 - a0 <= 180 ? 0 : 1;
    return `M ${p0.x} ${p0.y} A ${r} ${r} 0 ${largeArc} 0 ${p1.x} ${p1.y}`;
  }

  const track = arcPath(startAngle, endAngle);
  const fillAngle = startAngle + (endAngle - startAngle) * (anim * (s / 100));
  const fill = arcPath(startAngle, fillAngle);

  return (
    <div className="glass p-5 flex items-center gap-5">
      <svg width="200" height="120" viewBox="0 0 200 120">
        <path d={track} stroke="rgba(48,54,61,0.9)" strokeWidth="14" fill="none" strokeLinecap="round" />
        <path
          d={fill}
          stroke={c}
          strokeWidth="14"
          fill="none"
          strokeLinecap="round"
          style={{ filter: "drop-shadow(0 0 12px rgba(0,212,255,0.14))" }}
        />
      </svg>
      <div className="min-w-0">
        <div className="text-[11px] tracking-[0.48em] uppercase" style={{ color: "var(--text-muted)" }}>
          UX Score
        </div>
        <div className="mt-1 font-mono text-5xl leading-none" style={{ color: c }}>
          {num}
        </div>
        <div className="mt-2 font-display text-lg font-bold" style={{ color: c }}>
          {uxLabel || "—"}
        </div>
      </div>
    </div>
  );
}

function ScreenshotCard({ shot }) {
  const [expanded, setExpanded] = useState(false);
  const [imgError, setImgError] = useState(false);
  const rel = String(shot.url_path || "");
  const imgUrl = rel.startsWith("http") ? rel : `${BASE_URL}${rel.startsWith("/") ? rel : `/${rel}`}`;
  const isIssue = shot.type === "issue";

  return (
    <>
      <div
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded(true);
          }
        }}
        onClick={() => setExpanded(true)}
        style={{
          background: "#0F1117",
          border: `1px solid ${isIssue ? "rgba(255,107,53,0.3)" : "#21262D"}`,
          borderRadius: "12px",
          overflow: "hidden",
          cursor: "pointer",
          transition: "all 0.2s",
        }}
      >
        <div
          style={{
            height: "160px",
            overflow: "hidden",
            background: "#161B22",
            position: "relative",
          }}
        >
          {!imgError ? (
            <img
              src={imgUrl}
              alt={String(shot.label || "")}
              style={{
                width: "100%",
                height: "100%",
                objectFit: "cover",
                objectPosition: "top",
              }}
              onError={() => setImgError(true)}
            />
          ) : (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                height: "100%",
                flexDirection: "column",
                gap: "8px",
              }}
            >
              <span style={{ fontSize: "32px" }}>🖼️</span>
              <span style={{ color: "#484F58", fontSize: "12px" }}>Screenshot unavailable</span>
            </div>
          )}
          {isIssue ? (
            <div
              style={{
                position: "absolute",
                top: "8px",
                right: "8px",
                background: "rgba(255,107,53,0.9)",
                borderRadius: "4px",
                padding: "2px 8px",
                fontSize: "11px",
                fontFamily: "DM Sans,sans-serif",
                fontWeight: 600,
                color: "white",
              }}
            >
              Issue Evidence
            </div>
          ) : null}
        </div>
        <div style={{ padding: "10px 12px" }}>
          <div
            style={{
              fontFamily: "DM Sans,sans-serif",
              fontSize: "13px",
              color: "#E6EDF3",
              fontWeight: 500,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {String(shot.label || "").replace(/_/g, " ")}
          </div>
          <div
            style={{
              fontFamily: "JetBrains Mono,monospace",
              fontSize: "11px",
              color: "#484F58",
              marginTop: "3px",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {String(shot.page_url || "")}
          </div>
        </div>
      </div>
      {expanded ? (
        <div
          onClick={() => setExpanded(false)}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 1000,
            background: "rgba(0,0,0,0.85)",
            backdropFilter: "blur(8px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "24px",
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: "#0F1117",
              border: "1px solid #30363D",
              borderRadius: "16px",
              overflow: "hidden",
              maxWidth: "900px",
              width: "100%",
              maxHeight: "90vh",
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div
              style={{
                padding: "16px 20px",
                borderBottom: "1px solid #21262D",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <div>
                <div
                  style={{
                    fontFamily: "Syne,sans-serif",
                    fontWeight: 700,
                    color: "#E6EDF3",
                    fontSize: "16px",
                  }}
                >
                  {String(shot.label || "").replace(/_/g, " ")}
                </div>
                <div
                  style={{
                    fontFamily: "JetBrains Mono,monospace",
                    fontSize: "12px",
                    color: "#8B949E",
                    marginTop: "3px",
                  }}
                >
                  {String(shot.page_url || "")}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setExpanded(false)}
                style={{
                  background: "#161B22",
                  border: "1px solid #30363D",
                  color: "#8B949E",
                  borderRadius: "6px",
                  padding: "6px 12px",
                  cursor: "pointer",
                  fontFamily: "DM Sans,sans-serif",
                }}
              >
                ✕ Close
              </button>
            </div>
            <div style={{ overflow: "auto", flex: 1 }}>
              <img src={imgUrl} alt={String(shot.label || "")} style={{ width: "100%", display: "block" }} />
            </div>
            <div
              style={{
                padding: "12px 20px",
                borderTop: "1px solid #21262D",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <span style={{ fontSize: "12px", color: "#484F58" }}>Captured: {String(shot.captured_at || "")}</span>
              <a
                href={imgUrl}
                download={String(shot.filename || "screenshot.png")}
                style={{
                  color: "#00D4FF",
                  fontSize: "13px",
                  textDecoration: "none",
                  fontFamily: "DM Sans,sans-serif",
                }}
              >
                ↓ Download
              </a>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}

function fmtDuration(meta) {
  if (!meta) return "—";
  if (typeof meta.duration === "string") return meta.duration;
  if (meta.duration_seconds != null) return `${meta.duration_seconds}s`;
  if (meta.start_time && meta.end_time) {
    const sec = Math.max(0, Math.round(meta.end_time - meta.start_time));
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}m ${String(s).padStart(2, "0")}s`;
  }
  if (meta.elapsed != null) return String(meta.elapsed);
  return "—";
}

function Stat({ icon: Icon, label, value, color }) {
  return (
    <div className="glass p-4">
      <div className="flex items-center gap-2">
        <Icon size={16} style={{ color }} />
        <div className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
          {label}
        </div>
      </div>
      <div className="mt-2 text-3xl font-mono font-semibold" style={{ color: "var(--text-primary)" }}>
        {value}
      </div>
    </div>
  );
}

function CompareCard({ label, value, color }) {
  return (
    <div className="glass p-4">
      <div className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
        {label}
      </div>
      <div className="mt-2 text-3xl font-mono font-semibold" style={{ color }}>
        {value}
      </div>
    </div>
  );
}

function IssueRow({ issue }) {
  const [open, setOpen] = useState(false);
  const sev = String(issue.severity || issue.level || "LOW");
  const url = issue.url || issue.page_url || issue.page || "";
  const el = issue.element || issue.element_selector || issue.selector || "";
  const userMsg = issue.user_message || issue.description || issue.message || "—";
  const fix = issue.improvement || issue.fix_suggestion || "—";
  const tech = issue.description || issue.message || "";
  const ev = issue.evidence || issue.screenshot_path;

  return (
    <>
      <tr
        onClick={() => setOpen((v) => !v)}
        className="cursor-pointer"
        style={{ background: "rgba(15,17,23,0.75)", border: "1px solid rgba(48,54,61,0.65)" }}
      >
        <td className="px-3 py-3">
          <SeverityBadge level={sev} />
        </td>
        <td className="px-3 py-3 font-mono truncate max-w-[220px]" title={url} style={{ color: "var(--text-secondary)" }}>
          {url || "—"}
        </td>
        <td className="px-3 py-3 font-mono truncate max-w-[160px]" title={el} style={{ color: "var(--text-muted)" }}>
          {el || "—"}
        </td>
        <td className="px-3 py-3 max-w-[280px] truncate" title={userMsg} style={{ color: "var(--text-primary)" }}>
          {userMsg}
        </td>
        <td className="px-3 py-3 max-w-[280px] truncate" title={fix} style={{ color: "var(--text-secondary)" }}>
          {fix}
        </td>
        <td className="px-3 py-3">
          {ev ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                window.open(evidenceFullUrl(ev), "_blank", "noopener,noreferrer");
              }}
              style={{
                background: "transparent",
                border: "1px solid rgba(0,212,255,0.4)",
                color: "#00D4FF",
                borderRadius: "6px",
                padding: "4px 10px",
                cursor: "pointer",
                fontSize: "12px",
                fontFamily: "DM Sans,sans-serif",
              }}
            >
              📸 View
            </button>
          ) : (
            <span style={{ color: "#484F58", fontSize: "12px" }}>—</span>
          )}
        </td>
      </tr>
      {open ? (
        <tr>
          <td colSpan={6}>
            <div className="glass p-4 -mt-2">
              <div className="text-xs tracking-[0.18em] uppercase mb-2" style={{ color: "var(--text-muted)" }}>
                Technical detail
              </div>
              <div className="text-sm font-mono" style={{ color: "var(--text-muted)" }}>
                {tech || "—"}
              </div>
              {ev ? (
                <div className="mt-3 rounded-xl overflow-hidden max-h-[320px]" style={{ border: "1px solid rgba(48,54,61,0.65)" }}>
                  <img src={evidenceFullUrl(ev)} alt="Evidence" style={{ width: "100%", display: "block" }} />
                </div>
              ) : null}
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}

export function Results() {
  const { runId: runIdParam } = useParams();
  const navigate = useNavigate();
  const runId = runIdParam ? decodeURIComponent(runIdParam) : null;

  const [runData, setRunData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isLive, setIsLive] = useState(false);
  const [usingMock, setUsingMock] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [compare, setCompare] = useState(null);
  const [screenshots, setScreenshots] = useState([]);
  const [tab, setTab] = useState("ALL");
  const pollingRef = useRef(null);

  const fetchRun = useCallback(async () => {
    try {
      if (runId) {
        const res = await fetch(API.getRun(runId));
        if (!res.ok) throw new Error("not found");
        const data = await res.json();
        setRunData(data);
        setUsingMock(false);
        const st = String(data.status ?? "").toLowerCase();
        setIsLive(st === "running" || st === "pending");
        return st === "running" || st === "pending";
      }
      const res = await fetch(API.getRuns);
      if (!res.ok) throw new Error("no runs");
      const list = await res.json();
      const runs = Array.isArray(list) ? list : list.runs ?? [];
      if (runs.length === 0) {
        setRunData(null);
        setUsingMock(false);
        setIsLive(false);
        return false;
      }
      const data = runs[0];
      setRunData(data);
      setUsingMock(false);
      const st = String(data.status ?? "").toLowerCase();
      setIsLive(st === "running" || st === "pending");
      return st === "running" || st === "pending";
    } catch {
      const mock = mockRuns.find((r) => r.id === runId) ?? (!runId ? mockRuns[0] : null);
      if (mock) {
        setRunData({
          run_id: mock.id,
          job_id: mock.id,
          url: mock.url,
          status: mock.status,
          risk_score: mock.risk_score,
          risk_level: mock.risk_level,
          ux_score: mock.ux_score ?? Math.max(0, 100 - Number(mock.risk_score ?? 0)),
          ux_label: mock.ux_label ?? mock.risk_level,
          summary: mock.summary,
          issues: mockIssues,
          report: { issues: mockIssues },
        });
        setUsingMock(true);
        setIsLive(false);
        return false;
      }
      setRunData(null);
      setUsingMock(false);
      setIsLive(false);
      return false;
    }
  }, [runId]);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      try {
        await fetchRun();
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [runId, fetchRun]);

  useEffect(() => {
    if (!isLive) {
      if (pollingRef.current) clearInterval(pollingRef.current);
      return;
    }
    pollingRef.current = setInterval(async () => {
      const still = await fetchRun();
      if (!still && pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    }, INTERVALS.resultsPoll);
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [isLive, fetchRun]);

  const activeRunId = runId ?? runData?.run_id ?? runData?.job_id ?? runData?.id ?? null;

  useEffect(() => {
    const id = activeRunId ? String(activeRunId) : "";
    if (!id) {
      setScreenshots([]);
      return;
    }
    let cancelled = false;
    fetch(API.getScreenshots(id))
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled) setScreenshots(Array.isArray(data?.screenshots) ? data.screenshots : []);
      })
      .catch(() => {
        if (!cancelled) setScreenshots([]);
      });
    return () => {
      cancelled = true;
    };
  }, [activeRunId]);

  const issues = useMemo(() => {
    if (!runData) return [];
    const raw = runData.issues ?? runData.report?.issues ?? [];
    if (!Array.isArray(raw)) return [];
    return raw.map((issue, idx) => ({
      ...issue,
      severity: issue.severity ?? issue.level ?? "LOW",
      type: issue.type ?? issue.issue_type ?? "Issue",
      url: issue.page_url ?? issue.url ?? issue.page ?? "",
      element: issue.element_selector ?? issue.element ?? issue.selector ?? "",
      description: issue.description ?? issue.message ?? "",
      user_message: issue.user_message ?? issue.message ?? issue.description ?? "",
      improvement: issue.improvement ?? issue.fix_suggestion ?? "",
      evidence: issue.screenshot_path ?? issue.evidence ?? null,
      id: issue.id ?? idx,
    }));
  }, [runData]);

  const tabs = useMemo(() => {
    const counts = { ALL: issues.length, CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
    for (const i of issues) {
      const s = String(i.severity || "").toUpperCase();
      if (s.includes("CRITICAL")) counts.CRITICAL += 1;
      else if (s.includes("HIGH")) counts.HIGH += 1;
      else if (s.includes("MEDIUM")) counts.MEDIUM += 1;
      else counts.LOW += 1;
    }
    return counts;
  }, [issues]);

  const filtered = useMemo(() => {
    if (tab === "ALL") return issues;
    return issues.filter((i) => String(i.severity || "").toUpperCase().includes(tab));
  }, [issues, tab]);

  async function onToggleCompare() {
    const next = !compareOpen;
    setCompareOpen(next);
    if (next && activeRunId && !compare) {
      try {
        const res = await fetch(API.compareRun(activeRunId));
        if (res.ok) setCompare(await res.json());
      } catch {
        setCompare(null);
      }
    }
  }

  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "60vh",
          flexDirection: "column",
          gap: "16px",
        }}
      >
        <div
          className="h-10 w-10 rounded-full border-[3px] border-[#21262D] border-t-[#00D4FF] animate-spin"
          style={{ boxSizing: "border-box" }}
        />
        <span style={{ color: "#8B949E", fontFamily: "DM Sans,sans-serif" }}>Loading results...</span>
        <GlassCard className="p-5 w-full max-w-md opacity-90">
          <LoadingSkeleton height={120} />
        </GlassCard>
      </div>
    );
  }

  if (!runData) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "60vh",
          flexDirection: "column",
          gap: "24px",
        }}
      >
        <div style={{ fontSize: "48px" }}>📊</div>
        <div style={{ textAlign: "center" }}>
          <h2
            style={{
              fontFamily: "Syne,sans-serif",
              color: "#E6EDF3",
              fontSize: "24px",
              fontWeight: 700,
              margin: 0,
            }}
          >
            No Results Found
          </h2>
          <p style={{ color: "#8B949E", marginTop: "8px", fontFamily: "DM Sans,sans-serif" }}>
            {runId ? `Run "${runId}" not found or still loading` : "Run a test first to see results here"}
          </p>
        </div>
        <div style={{ display: "flex", gap: "12px" }}>
          <button
            type="button"
            onClick={() => navigate("/new-test")}
            style={{
              background: "linear-gradient(135deg,#00D4FF,#7C3AED)",
              color: "#0A0C10",
              border: "none",
              borderRadius: "8px",
              padding: "10px 20px",
              fontFamily: "DM Sans,sans-serif",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Run New Test
          </button>
          <button
            type="button"
            onClick={() => navigate("/history")}
            style={{
              background: "transparent",
              border: "1px solid #30363D",
              color: "#8B949E",
              borderRadius: "8px",
              padding: "10px 20px",
              fontFamily: "DM Sans,sans-serif",
              cursor: "pointer",
            }}
          >
            View History
          </button>
        </div>
      </div>
    );
  }

  const riskNum = Number(runData?.risk_score ?? runData?.riskScore ?? 0);
  const uxScore = runData?.ux_score != null ? Number(runData.ux_score) : Math.max(0, 100 - riskNum);
  const uxLabel = runData?.ux_label ?? runData?.risk_level ?? "—";
  const uxColor = runData?.ux_color ?? null;
  const uxSummary = runData?.ux_summary ?? null;
  const topFixes = Array.isArray(runData?.top_improvements) ? runData.top_improvements : [];
  const catScores = runData?.category_scores && typeof runData.category_scores === "object" ? runData.category_scores : {};
  const passed = Array.isArray(runData?.passed_checks) ? runData.passed_checks : [];

  const summary = runData?.summary || {};
  const duration = fmtDuration(runData);
  const pages = summary.total_pages_scanned ?? runData?.pages_scanned ?? runData?.pages ?? 0;
  const actions = summary.total_actions_run ?? runData?.actions_run ?? runData?.actions ?? 0;
  const issueCount = summary.total_issues_found ?? issues.length ?? 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="grid gap-6 md:ml-[240px]"
    >
      {isLive ? (
        <div
          style={{
            background: "rgba(0,212,255,0.08)",
            border: "1px solid rgba(0,212,255,0.3)",
            borderRadius: "8px",
            padding: "10px 16px",
            display: "flex",
            alignItems: "center",
            gap: "10px",
          }}
        >
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: "#00D4FF",
              animation: "pulse 1.5s ease-in-out infinite",
            }}
          />
          <span style={{ color: "#00D4FF", fontSize: "13px", fontFamily: "DM Sans,sans-serif" }}>
            QA test in progress — results updating live every 2s
          </span>
        </div>
      ) : null}

      {usingMock ? (
        <div
          style={{
            background: "rgba(245,166,35,0.08)",
            border: "1px solid rgba(245,166,35,0.3)",
            borderRadius: "8px",
            padding: "10px 16px",
          }}
        >
          <span style={{ color: "#F5A623", fontSize: "13px" }}>⚠ Using demo data — backend offline</span>
        </div>
      ) : null}

      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="font-display text-2xl font-extrabold">Results</div>
          <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
            {activeRunId ? (
              <>
                Run <span className="font-mono" style={{ color: uxColor || "var(--accent-cyan)" }}>{String(activeRunId).slice(0, 12)}</span>
              </>
            ) : (
              "No runs available"
            )}
          </div>
        </div>
        <Link
          to="/new-test"
          className="h-11 px-4 rounded-xl font-semibold inline-flex items-center"
          style={{ background: "rgba(0,212,255,0.14)", color: "var(--accent-cyan)", border: "1px solid rgba(0,212,255,0.35)" }}
        >
          New Test
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <UXScoreGauge uxScore={uxScore} uxLabel={uxLabel} />
        <GlassCard className="p-5">
          <div className="grid gap-3 md:grid-cols-2">
            <Stat icon={FileSearch} label="Pages Scanned" value={pages ?? "—"} color="var(--accent-cyan)" />
            <Stat icon={MousePointer} label="Actions Run" value={actions ?? "—"} color="var(--text-primary)" />
            <Stat icon={AlertCircle} label="Issues Found" value={issueCount ?? issues.length ?? 0} color="var(--warning)" />
            <Stat icon={Timer} label="Test Duration" value={duration} color="var(--text-secondary)" />
          </div>
          <div className="mt-4 flex items-center justify-between gap-3">
            <div className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
              Risk score (inverse of UX)
            </div>
            <span className="font-display text-sm font-bold text-right" style={{ color: uxColor || uxColorForScore(uxScore) }}>
              {uxLabel}
            </span>
          </div>
        </GlassCard>
      </div>

      {uxSummary ? (
        <div
          style={{
            background: "#0F1117",
            border: "1px solid #21262D",
            borderRadius: "12px",
            padding: "20px 24px",
          }}
        >
          <div
            style={{
              fontSize: "11px",
              color: "#484F58",
              fontFamily: "DM Sans,sans-serif",
              marginBottom: "8px",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
            }}
          >
            UX Assessment
          </div>
          <p
            style={{
              color: "#E6EDF3",
              fontSize: "15px",
              fontFamily: "DM Sans,sans-serif",
              lineHeight: "1.6",
              margin: 0,
            }}
          >
            {uxSummary}
          </p>
        </div>
      ) : null}

      {topFixes.length > 0 ? (
        <div style={{ marginTop: "8px" }}>
          <h3
            style={{
              fontFamily: "Syne,sans-serif",
              fontWeight: 700,
              color: "#E6EDF3",
              fontSize: "18px",
              marginBottom: "16px",
              display: "flex",
              alignItems: "center",
              gap: "10px",
              flexWrap: "wrap",
            }}
          >
            🔧 Top Improvements
            <span style={{ fontSize: "13px", color: "#8B949E", fontWeight: 400 }}>
              Fix these first for maximum UX impact
            </span>
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {topFixes.map((fix, i) => (
              <div
                key={i}
                style={{
                  background: "#0F1117",
                  border: `1px solid ${
                    fix.impact === "CRITICAL"
                      ? "rgba(255,68,68,0.3)"
                      : fix.impact === "HIGH"
                        ? "rgba(255,107,53,0.3)"
                        : "rgba(245,166,35,0.2)"
                  }`,
                  borderRadius: "12px",
                  padding: "16px 20px",
                  display: "flex",
                  gap: "16px",
                  alignItems: "flex-start",
                }}
              >
                <div
                  style={{
                    width: "32px",
                    height: "32px",
                    borderRadius: "50%",
                    background:
                      fix.impact === "CRITICAL"
                        ? "rgba(255,68,68,0.2)"
                        : fix.impact === "HIGH"
                          ? "rgba(255,107,53,0.2)"
                          : "rgba(245,166,35,0.2)",
                    border: `1px solid ${
                      fix.impact === "CRITICAL" ? "#FF4444" : fix.impact === "HIGH" ? "#FF6B35" : "#F5A623"
                    }`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontFamily: "JetBrains Mono,monospace",
                    fontWeight: 700,
                    fontSize: "14px",
                    flexShrink: 0,
                    color: fix.impact === "CRITICAL" ? "#FF4444" : fix.impact === "HIGH" ? "#FF6B35" : "#F5A623",
                  }}
                >
                  {fix.priority}
                </div>
                <div style={{ flex: 1 }}>
                  <div
                    style={{
                      display: "flex",
                      gap: "8px",
                      alignItems: "center",
                      marginBottom: "6px",
                      flexWrap: "wrap",
                    }}
                  >
                    <span
                      style={{
                        background:
                          fix.impact === "CRITICAL"
                            ? "rgba(255,68,68,0.15)"
                            : fix.impact === "HIGH"
                              ? "rgba(255,107,53,0.15)"
                              : "rgba(245,166,35,0.15)",
                        color: fix.impact === "CRITICAL" ? "#FF4444" : fix.impact === "HIGH" ? "#FF6B35" : "#F5A623",
                        borderRadius: "4px",
                        padding: "2px 8px",
                        fontSize: "11px",
                        fontFamily: "DM Sans,sans-serif",
                        fontWeight: 600,
                      }}
                    >
                      {fix.impact}
                    </span>
                    <span style={{ fontSize: "12px", color: "#8B949E", fontFamily: "DM Sans,sans-serif" }}>{fix.category}</span>
                  </div>
                  <p
                    style={{
                      color: "#E6EDF3",
                      fontSize: "14px",
                      fontFamily: "DM Sans,sans-serif",
                      lineHeight: "1.5",
                      margin: "0 0 6px 0",
                    }}
                  >
                    {fix.action}
                  </p>
                  <div style={{ fontSize: "12px", color: "#484F58", fontFamily: "DM Sans,sans-serif" }}>👥 Affects: {fix.affects}</div>
                </div>
                <div style={{ textAlign: "center", flexShrink: 0 }}>
                  <div style={{ fontFamily: "JetBrains Mono,monospace", fontSize: "18px", fontWeight: 600, color: "#00C896" }}>
                    +{fix.penalty_removed}
                  </div>
                  <div style={{ fontSize: "10px", color: "#484F58", fontFamily: "DM Sans,sans-serif" }}>UX pts</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {Object.keys(catScores).length > 0 ? (
        <div style={{ marginTop: "8px" }}>
          <h3 style={{ fontFamily: "Syne,sans-serif", fontWeight: 700, color: "#E6EDF3", fontSize: "18px", marginBottom: "16px" }}>
            📊 UX Category Breakdown
          </h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "12px" }}>
            {Object.entries(catScores).map(([cat, data]) => {
              const scoreColor =
                data.score >= 90 ? "#00C896" : data.score >= 75 ? "#00D4FF" : data.score >= 55 ? "#F5A623" : data.score >= 35 ? "#FF6B35" : "#FF4444";
              return (
                <div key={cat} style={{ background: "#0F1117", border: "1px solid #21262D", borderRadius: "10px", padding: "14px 16px" }}>
                  <div style={{ fontFamily: "DM Sans,sans-serif", fontSize: "13px", color: "#8B949E", marginBottom: "8px" }}>{cat}</div>
                  <div style={{ background: "#21262D", borderRadius: "4px", height: "6px", marginBottom: "8px", overflow: "hidden" }}>
                    <div
                      style={{
                        width: `${data.score}%`,
                        height: "100%",
                        background: scoreColor,
                        borderRadius: "4px",
                        transition: "width 1s ease-out",
                      }}
                    />
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontFamily: "JetBrains Mono,monospace", fontSize: "20px", fontWeight: 600, color: scoreColor }}>{data.score}</span>
                    <span style={{ fontSize: "12px", color: scoreColor, fontFamily: "DM Sans,sans-serif" }}>{data.label}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {passed.length > 0 ? (
        <div style={{ marginTop: "8px", background: "#0F1117", border: "1px solid rgba(0,200,150,0.2)", borderRadius: "12px", padding: "16px 20px" }}>
          <div style={{ fontSize: "13px", color: "#00C896", fontFamily: "DM Sans,sans-serif", fontWeight: 600, marginBottom: "12px" }}>✅ What's Working Well</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
            {passed.map((p, i) => (
              <span
                key={i}
                style={{
                  background: "rgba(0,200,150,0.1)",
                  border: "1px solid rgba(0,200,150,0.2)",
                  borderRadius: "20px",
                  padding: "4px 12px",
                  fontSize: "13px",
                  color: "#00C896",
                  fontFamily: "DM Sans,sans-serif",
                }}
              >
                {p}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <GlassCard className="p-5">
        <div className="flex items-center justify-between gap-3">
          <div className="font-display font-bold text-lg">Issues</div>
          <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
            {issues.length} total
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"].map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className="px-3 py-2 rounded-xl text-sm font-semibold"
              style={{
                background: tab === t ? "rgba(0,212,255,0.14)" : "rgba(22,27,34,0.75)",
                color: tab === t ? "var(--accent-cyan)" : "var(--text-secondary)",
                border: "1px solid rgba(48,54,61,0.7)",
              }}
            >
              {t} ({tabs[t] ?? 0})
            </button>
          ))}
        </div>

        <div className="mt-4 overflow-auto no-scrollbar">
          <table className="w-full text-sm" style={{ borderCollapse: "separate", borderSpacing: "0 10px" }}>
            <thead>
              <tr className="text-xs uppercase tracking-[0.18em]" style={{ color: "var(--text-muted)" }}>
                <th className="text-left px-3">Severity</th>
                <th className="text-left px-3">Page URL</th>
                <th className="text-left px-3">Element</th>
                <th className="text-left px-3">User view</th>
                <th className="text-left px-3">How to fix</th>
                <th className="text-left px-3">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((i, idx) => (
                <IssueRow key={i.id ?? `${idx}`} issue={i} />
              ))}
              {!filtered.length ? (
                <tr>
                  <td colSpan={6}>
                    <div className="mt-3 glass p-8 text-center">
                      <div className="text-lg font-display font-bold" style={{ color: "var(--success)" }}>
                        No {tab === "ALL" ? "" : `${tab.toLowerCase()} `}issues found
                      </div>
                      <div className="text-sm mt-2" style={{ color: "var(--text-secondary)" }}>
                        This view is empty for the selected severity filter.
                      </div>
                    </div>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </GlassCard>

      {screenshots.length > 0 ? (
        <div style={{ marginTop: "8px" }}>
          <h3 style={{ fontFamily: "Syne,sans-serif", fontWeight: 700, color: "#E6EDF3", fontSize: "18px", marginBottom: "16px" }}>📸 Execution Screenshots</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "16px" }}>
            {screenshots.map((shot, i) => (
              <ScreenshotCard key={`${shot.filename || i}-${i}`} shot={shot} />
            ))}
          </div>
        </div>
      ) : null}

      {screenshots.length === 0 && issues.length > 0 ? (
        <div
          style={{
            marginTop: "8px",
            padding: "24px",
            background: "#0F1117",
            border: "1px solid #21262D",
            borderRadius: "12px",
            textAlign: "center",
          }}
        >
          <span style={{ color: "#484F58", fontSize: "14px" }}>No screenshots captured for this run</span>
        </div>
      ) : null}

      <GlassCard className="p-5">
        <button type="button" className="w-full flex items-center justify-between" onClick={onToggleCompare}>
          <div className="font-display font-bold text-lg">Compare with Previous Run</div>
          <ChevronDown size={18} style={{ transform: compareOpen ? "rotate(180deg)" : "rotate(0deg)" }} />
        </button>
        {compareOpen ? (
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <CompareCard label="New Issues" value={compare?.new_issues?.length ?? "—"} color="var(--danger)" />
            <CompareCard label="Resolved Issues" value={compare?.resolved_issues?.length ?? "—"} color="var(--success)" />
            <CompareCard label="Score Delta" value={compare?.regression_score_delta ?? "—"} color="var(--warning)" />
          </div>
        ) : null}
      </GlassCard>
    </motion.div>
  );
}
