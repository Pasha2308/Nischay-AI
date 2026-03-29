import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { JobEvent } from "../services/backend-service";

const STAGGER_MS = 95;

const PHASE_LABELS = ["Crawling", "Executing", "Analyzing", "Reporting"] as const;

/** Icons: crawl · execute · analyze · success · error · warning */
export function iconForLogEntry(ev: JobEvent): string {
  const t = (ev.type || "").toLowerCase();
  const name = (ev.name || "").toLowerCase();
  const msg = (ev.message || "").toLowerCase();

  if (t === "error") return "❌";
  if (t === "success") return "✅";
  if (t === "warning" || msg.includes("warning")) return "⚠️";

  if (t === "crawler" || name.includes("crawl") || msg.includes("crawl")) return "🌐";
  if (t === "stage") {
    if (name.includes("phase_1") || name.includes("crawl")) return "🌐";
    if (name.includes("phase_2") || name.includes("execution")) return "⚡";
    if (name.includes("phase_3") || name.includes("ai_analysis")) return "🧠";
    if (name.includes("phase_4") || name.includes("report")) return "⚡";
  }
  if (t === "evaluator") return "🧠";
  if (t === "execution") return "⚡";
  if (t === "action") {
    if (msg.includes("summary") || msg.includes("generating") || msg.includes("ai")) return "🧠";
    return "⚡";
  }
  if (t === "detection") return "🌐";
  if (msg.includes("ai summary") || msg.includes("generating")) return "🧠";

  return "⚡";
}

function deriveActivePhaseIndex(events: JobEvent[]): number {
  let step = 0;
  for (const ev of events) {
    const n = (ev.name || "").toLowerCase();
    if (ev.type === "evaluator") {
      step = Math.max(step, 2);
      continue;
    }
    if (ev.type === "stage") {
      if (n.includes("phase_4") || n.includes("report")) step = 3;
      else if (n.includes("phase_3") || n.includes("ai_analysis")) step = 2;
      else if (n.includes("phase_2") || n.includes("execution")) step = 1;
      else if (n.includes("phase_1") || n.includes("crawl")) step = 0;
    }
    if (n === "crawl_complete") step = Math.max(step, 1);
    if (n === "execution_complete") step = Math.max(step, 2);
  }
  return Math.min(step, 3);
}

function hasScanCompleteEvent(events: JobEvent[]): boolean {
  return events.some((e) => (e.message || "").toUpperCase().includes("SCAN COMPLETE"));
}

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  if (h > 0) {
    return `${h}:${String(m % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

export type LiveScanLogProps = {
  events: JobEvent[];
  /** Target URL for the current run */
  targetUrl?: string;
  /** Human-readable scan task label */
  scanTaskLabel?: string;
  /** Job id for results link */
  jobId?: string | null;
  /** Epoch ms when the run started (enables elapsed timer) */
  startedAtMs?: number | null;
};

export function LiveScanLog({
  events,
  targetUrl = "",
  scanTaskLabel = "",
  jobId = null,
  startedAtMs = null,
}: LiveScanLogProps) {
  const logRef = useRef<HTMLDivElement>(null);
  const [visibleCount, setVisibleCount] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  const scanComplete = hasScanCompleteEvent(events);
  const activePhase = deriveActivePhaseIndex(events);

  useEffect(() => {
    if (startedAtMs == null) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [startedAtMs]);

  useEffect(() => {
    if (events.length === 0) {
      setVisibleCount(0);
      return;
    }
    if (visibleCount >= events.length) return;
    const t = window.setTimeout(() => {
      setVisibleCount((c) => Math.min(c + 1, events.length));
    }, STAGGER_MS);
    return () => window.clearTimeout(t);
  }, [events, events.length, visibleCount]);

  useLayoutEffect(() => {
    const el = logRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [events.length, visibleCount]);

  const visible = events.slice(0, visibleCount);

  const elapsedMs =
    startedAtMs != null ? Math.max(0, now - startedAtMs) : null;

  const displayUrl =
    targetUrl.length > 56 ? `${targetUrl.slice(0, 54)}…` : targetUrl || "—";

  return (
    <div className="card log-card live-scan-log">
      <div className="live-scan-stepper" aria-label="Pipeline progress">
        {PHASE_LABELS.map((label, i) => {
          const done = scanComplete || i < activePhase;
          const current = !scanComplete && i === activePhase;
          return (
            <div key={label} className="live-scan-stepper-item">
              {i > 0 && (
                <span
                  className={`live-scan-stepper-arrow ${done ? "is-done" : ""}`}
                  aria-hidden
                >
                  →
                </span>
              )}
              <span
                className={[
                  "live-scan-stepper-label",
                  done ? "is-done" : "",
                  current ? "is-current" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                {label}
              </span>
            </div>
          );
        })}
      </div>

      <div className="live-scan-topbar">
        <div className="live-scan-topbar-url" title={targetUrl || undefined}>
          <span className="live-scan-topbar-k">URL</span>
          <span className="live-scan-topbar-v">{displayUrl}</span>
        </div>
        <div className="live-scan-topbar-meta">
          <span className="live-scan-topbar-k">Task</span>
          <span className="live-scan-topbar-v">{scanTaskLabel || "—"}</span>
        </div>
        <div className="live-scan-topbar-time">
          <span className="live-scan-topbar-k">Elapsed</span>
          <span className="live-scan-topbar-v live-scan-timer" aria-live="polite">
            {elapsedMs != null ? formatElapsed(elapsedMs) : "—"}
          </span>
        </div>
      </div>

      <div className="card-title live-scan-log-title">Live Scan Activity</div>
      <div className="log-panel live-scan-log-panel" ref={logRef}>
        {visible.map((ev, idx) => (
          <div
            key={`${ev.time}-${idx}`}
            className={`log-row log-row--enter ${ev.type}`}
          >
            <span className="log-icon" aria-hidden="true" title={ev.type}>
              {iconForLogEntry(ev)}
            </span>
            <span className="log-time">{new Date(ev.time * 1000).toLocaleTimeString()}</span>
            <span className="log-msg">{ev.message}</span>
          </div>
        ))}
        {!events.length && <div className="muted log-placeholder">Waiting for scan events...</div>}
      </div>

      {scanComplete && jobId && (
        <div className="live-scan-results-cta">
          <Link className="btn-primary live-scan-results-btn" to={`/results/${jobId}`}>
            View Results →
          </Link>
        </div>
      )}
    </div>
  );
}
