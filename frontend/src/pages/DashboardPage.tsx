import { useEffect, useMemo, useRef, useState } from "react";
import { fetchDemo, fetchJobEvents, fetchResults, triggerTestRun, type JobEvent } from "../services/backend-service";
import { KpiCard } from "../components/KpiCard";
import { LineChart } from "../components/LineChart";
import { ActivityFeed } from "../components/ActivityFeed";
import { loadScans, saveScans, upsertScan } from "../store/scanStore";
import { toScanRecord, type ScanRecord } from "../types";
import { seedScans } from "../data/seed";

export function DashboardPage() {
  const [url, setUrl] = useState("https://example.com");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [requiresLogin, setRequiresLogin] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [scans, setScans] = useState<ScanRecord[]>(() => loadScans());
  const [events, setEvents] = useState<JobEvent[]>([]);
  const logRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!logRef.current) return;
    logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [events]);

  const kpis = useMemo(() => {
    const total = scans.length;
    const defects = scans.reduce((n, s) => n + s.defectCount, 0);
    const avg = total ? Math.round(scans.reduce((n, s) => n + s.riskScore, 0) / total) : 0;
    const sites = new Set(scans.map((s) => new URL(s.url).hostname)).size;
    return { total, defects, avg, sites };
  }, [scans]);

  const points = scans
    .slice(0, 7)
    .reverse()
    .map((s, i) => ({ xLabel: `#${i + 1}`, y: s.riskScore }));

  async function runDemoNow() {
    setBusy(true);
    try {
      if (scans.length < 10) {
        const seeded = seedScans();
        saveScans(seeded);
        setScans(seeded);
        setMsg("Demo dataset loaded (12 scans)");
      } else {
        const payload = await fetchDemo();
        const rec = toScanRecord({
          id: `scan_demo_${Date.now()}`,
          url: "https://stripe.com",
          projectId: "p1",
          projectName: "Marketing Site",
          result: payload,
        });
        setScans(upsertScan(rec));
        setMsg("Demo result loaded");
      }
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runScan() {
    setBusy(true);
    setMsg("Scanning...");
    setEvents([]);
    try {
      if (requiresLogin && (!username.trim() || !password.trim())) {
        setMsg("Enter username and password for authenticated scan.");
        return;
      }
      const authPayload =
        requiresLogin && username.trim() && password.trim()
          ? { username: username.trim(), password }
          : undefined;
      const started = await triggerTestRun(url, authPayload);
      const jobId = started.job_id;
      // simple polling loop
      for (let i = 0; i < 50; i++) {
        const [latest, jobEvents] = await Promise.all([fetchResults(jobId), fetchJobEvents(jobId)]);
        setEvents(jobEvents);
        if (latest.status === "completed" && latest.result) {
          const rec = toScanRecord({ id: `scan_${Date.now()}`, url, result: latest.result });
          setScans(upsertScan(rec));
          setMsg("Scan complete");
          break;
        }
        if (latest.status === "failed") {
          setMsg(latest.error ?? "Scan failed");
          break;
        }
        await new Promise((r) => setTimeout(r, 1500));
      }
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
      setPassword("");
    }
  }

  if (scans.length === 0) {
    return (
      <div className="page">
        <div className="card onboarding-card">
          <h1>Welcome to ReQon Scout</h1>
          <p className="muted">Run autonomous QA scans in minutes and get instant risk visibility.</p>
          <div className="toolbar">
            <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com" />
            <button className="btn-primary" onClick={runScan} disabled={busy}>
              {busy ? "Scanning..." : "Start Scan"}
            </button>
            <button onClick={runDemoNow} disabled={busy}>
              Load Demo Data
            </button>
          </div>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={requiresLogin}
              onChange={(e) => setRequiresLogin(e.target.checked)}
            />
            This site requires login
          </label>
          {requiresLogin && (
            <div className="auth-grid">
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Username or email"
                autoComplete="username"
              />
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
                type="password"
                autoComplete="current-password"
              />
            </div>
          )}
          {busy && <div className="scanning-indicator" aria-live="polite">Scanning<span className="dots" /></div>}
          {msg && <p className="muted">{msg}</p>}
          {(busy || events.length > 0) && (
            <div className="card log-card">
              <div className="card-title">Live Scan Activity</div>
              <div className="log-panel" ref={logRef}>
                {events.map((ev, idx) => (
                  <div key={`${ev.time}-${idx}`} className={`log-row ${ev.type}`}>
                    <span className="log-time">{new Date(ev.time * 1000).toLocaleTimeString()}</span>
                    <span className="log-msg">{ev.message}</span>
                  </div>
                ))}
                {!events.length && <div className="muted">Waiting for scan events...</div>}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="toolbar">
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com" />
        <button onClick={runScan} disabled={busy}>{busy ? "Scanning..." : "Scan"}</button>
        <button onClick={runDemoNow} disabled={busy}>Run Demo</button>
      </div>
      <label className="toggle-row">
        <input
          type="checkbox"
          checked={requiresLogin}
          onChange={(e) => setRequiresLogin(e.target.checked)}
        />
        This site requires login
      </label>
      {requiresLogin && (
        <div className="auth-grid">
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Username or email"
            autoComplete="username"
          />
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            type="password"
            autoComplete="current-password"
          />
        </div>
      )}
      {busy && <div className="scanning-indicator" aria-live="polite">Scanning<span className="dots" /></div>}
      {msg && <p className="muted">{msg}</p>}
      {(busy || events.length > 0) && (
        <div className="card log-card">
          <div className="card-title">Live Scan Activity</div>
          <div className="log-panel" ref={logRef}>
            {events.map((ev, idx) => (
              <div key={`${ev.time}-${idx}`} className={`log-row ${ev.type}`}>
                <span className="log-time">{new Date(ev.time * 1000).toLocaleTimeString()}</span>
                <span className="log-msg">{ev.message}</span>
              </div>
            ))}
            {!events.length && <div className="muted">Waiting for scan events...</div>}
          </div>
        </div>
      )}
      <div className="kpi-grid">
        <KpiCard label="Total scans" value={kpis.total} />
        <KpiCard label="Defects found" value={kpis.defects} />
        <KpiCard label="Avg risk score" value={kpis.avg} />
        <KpiCard label="Sites covered" value={kpis.sites} />
      </div>
      <LineChart title="Risk Score (last 7 scans)" points={points} />
      <ActivityFeed scans={scans} />
    </div>
  );
}

