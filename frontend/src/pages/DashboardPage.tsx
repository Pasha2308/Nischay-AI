import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Link } from "react-router-dom";
import {
  fetchJobEvents,
  fetchJobStatus,
  fetchResults,
  triggerTestRun,
  type JobEvent,
} from "../services/backend-service";
import { LiveScanLog } from "../components/LiveScanLog";
import { upsertScan } from "../store/scanStore";
import { toScanRecord } from "../types";

/** Preset journey bundles (expanded server-side via TASK_GROUPS). */
const SCAN_TASK_PRESETS = [
  { value: "quick_scan", label: "Quick Scan" },
  { value: "conversion_scan", label: "Conversion Flow" },
  { value: "auth_scan", label: "Authentication Flow" },
  { value: "full_app_scan", label: "Full App Scan" },
];

/** Single fast micro-tasks (backend run_micro_task). */
const QUICK_ACTIONS = [
  { value: "search_product", label: "Search Product" },
  { value: "add_to_cart", label: "Add to Cart" },
  { value: "fill_checkout", label: "Checkout Form" },
  { value: "contact_support", label: "Contact Support" },
] as const;

/** Individual flows for Advanced mode (matches backend ECOMMERCE_FLOWS keys). */
const ADVANCED_FLOW_IDS = [
  "auth",
  "browse",
  "product",
  "cart",
  "checkout",
  "support",
  "ui",
  "navigation",
  "search",
  "coupon",
] as const;

function LoginWaitBanner() {
  return (
    <div className="login-wait-banner" role="status" aria-live="polite">
      <p className="login-wait-banner-title">
        🔐 Browser window opened — please log in to continue
      </p>
      <p className="login-wait-banner-sub">Waiting for user authentication...</p>
      <div className="login-wait-banner-footer">
        <span className="spinner" aria-hidden="true" />
        <span>Waiting up to 2 minutes</span>
      </div>
    </div>
  );
}

export function DashboardPage() {
  const navigate = useNavigate();
  const [url, setUrl] = useState("https://automationexercise.com");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [scanTask, setScanTask] = useState("full_app_scan");
  const [executionMode, setExecutionMode] = useState<"full" | "quick_action">("full");
  const [microTask, setMicroTask] = useState<string>("search_product");
  const [isAdvancedMode, setIsAdvancedMode] = useState(false);
  const [advancedFlows, setAdvancedFlows] = useState<string[]>([]);
  const [scanMode, setScanMode] = useState<"fast" | "deep">("fast");
  const [requiresLogin, setRequiresLogin] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginUrl, setLoginUrl] = useState("");
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [jobStatus, setJobStatus] = useState<string>("");
  const [liveJobId, setLiveJobId] = useState<string | null>(null);
  const [scanStartedAt, setScanStartedAt] = useState<number | null>(null);

  const toggleFlow = (flow: string) => {
    setAdvancedFlows((prev) =>
      prev.includes(flow) ? prev.filter((f) => f !== flow) : [...prev, flow],
    );
  };

  async function runScan() {
    const target = url.trim();
    if (!target) {
      setMsg("Enter a URL to scan.");
      return;
    }
    if (requiresLogin) {
      if (!username.trim() || !password.trim()) {
        setMsg("Enter username and password for authenticated scan.");
        return;
      }
      const lu = loginUrl.trim() || target;
      if (!lu.startsWith("http://") && !lu.startsWith("https://")) {
        setMsg("Login URL must be a valid http(s) URL (or leave blank to use the scan URL).");
        return;
      }
    }

    setBusy(true);
    setMsg("Scanning...");
    setEvents([]);
    try {
      const credentials =
        requiresLogin && username.trim() && password.trim()
          ? {
              username: username.trim(),
              password,
              login_url: loginUrl.trim() || target,
            }
          : undefined;

      const started =
        executionMode === "quick_action"
          ? await triggerTestRun(target, {
              task_type: "micro",
              micro_task: microTask,
              scan_mode: scanMode,
              requires_login: requiresLogin,
              credentials,
            })
          : await triggerTestRun(target, {
              ...(isAdvancedMode
                ? {
                    flows:
                      advancedFlows.length > 0 ? advancedFlows : ["quick_scan"],
                  }
                : { scan_task: scanTask }),
              scan_mode: scanMode,
              requires_login: requiresLogin,
              credentials,
            });
      const jobId = started.job_id;
      setLiveJobId(jobId);
      setScanStartedAt(Date.now());

      for (let i = 0; i < 50; i++) {
        const [latest, jobEvents, jobSt] = await Promise.all([
          fetchResults(jobId),
          fetchJobEvents(jobId),
          fetchJobStatus(jobId),
        ]);
        setEvents(jobEvents);
        setJobStatus(jobSt.status);
        if (jobSt.status === "WAITING_FOR_LOGIN") {
          setMsg(jobSt.message || "Please login in the Chrome window");
        }
        if (
          (latest.status === "complete" || latest.status === "completed") &&
          latest.result
        ) {
          const rec = toScanRecord({
            id: `scan_${Date.now()}`,
            url: target,
            result: latest.result,
          });
          upsertScan(rec);
          setMsg("Scan complete");
          navigate(`/results/${jobId}`);
          break;
        }
        if (latest.status === "partial" && latest.result) {
          const rec = toScanRecord({
            id: `scan_${Date.now()}`,
            url: target,
            result: latest.result,
            status: "failed",
          });
          upsertScan(rec);
          setMsg(latest.result.warning ?? "Scan timed out — showing partial results");
          navigate(`/results/${jobId}`);
          break;
        }
        if (latest.status === "failed") {
          setMsg(latest.error ?? "Scan failed");
          navigate(`/results/${jobId}`);
          break;
        }
        await new Promise((r) => setTimeout(r, 2000));
      }
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
      setPassword("");
    }
  }

  return (
    <div className="page launch-page">
      <section className="launch-hero">
        <h1 className="launch-hero-title">Find what breaks before your users do</h1>
        <p className="launch-hero-subtitle">
          Autonomous QA scanning for any web application
        </p>
      </section>

      <div className="launch-card card">
        <div className="launch-url-wrap">
          <label className="launch-field-label" htmlFor="launch-url">
            Target URL
          </label>
          <input
            id="launch-url"
            className="launch-url-input"
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://your-app.com"
            disabled={busy}
            autoComplete="url"
          />
        </div>

        <div className="launch-controls">
          <div className="launch-control launch-control--wide">
            <span className="launch-field-label">Execution mode</span>
            <div className="launch-segment" role="group" aria-label="Execution mode">
              <button
                type="button"
                className={`launch-segment-btn ${executionMode === "full" ? "is-active" : ""}`}
                onClick={() => {
                  setExecutionMode("full");
                }}
                disabled={busy}
              >
                Full scan
              </button>
              <button
                type="button"
                className={`launch-segment-btn ${executionMode === "quick_action" ? "is-active" : ""}`}
                onClick={() => {
                  setExecutionMode("quick_action");
                  setIsAdvancedMode(false);
                }}
                disabled={busy}
              >
                Quick Action Mode
              </button>
            </div>
            {executionMode === "quick_action" ? (
              <>
                <label className="launch-field-label launch-field-label--spaced" htmlFor="launch-micro-task">
                  Quick action
                </label>
                <select
                  id="launch-micro-task"
                  className="launch-select"
                  value={microTask}
                  onChange={(e) => setMicroTask(e.target.value)}
                  disabled={busy}
                >
                  {QUICK_ACTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <p className="muted launch-micro-hint">
                  Runs one fast task (~20s) — ideal for demos.
                </p>
              </>
            ) : (
              <>
                <label className="launch-field-label" htmlFor="launch-scan-task">
                  Journey preset
                </label>
                <select
                  id="launch-scan-task"
                  className="launch-select"
                  value={scanTask}
                  onChange={(e) => setScanTask(e.target.value)}
                  disabled={busy || isAdvancedMode}
                >
                  {SCAN_TASK_PRESETS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <label className="launch-toggle launch-toggle--inline">
                  <input
                    type="checkbox"
                    checked={isAdvancedMode}
                    onChange={(e) => setIsAdvancedMode(e.target.checked)}
                    disabled={busy}
                  />
                  <span>Advanced (pick flows)</span>
                </label>
                {isAdvancedMode && (
                  <div className="launch-adv-flows" role="group" aria-label="Flows to run">
                    {ADVANCED_FLOW_IDS.map((flow) => (
                      <label key={flow} className="launch-adv-flow-chip">
                        <input
                          type="checkbox"
                          checked={advancedFlows.includes(flow)}
                          onChange={() => toggleFlow(flow)}
                          disabled={busy}
                        />
                        <span>{flow}</span>
                      </label>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>

          <div className="launch-control">
            <span className="launch-field-label">Scan depth</span>
            <div className="launch-segment" role="group" aria-label="Scan depth">
              <button
                type="button"
                className={`launch-segment-btn ${scanMode === "fast" ? "is-active" : ""}`}
                onClick={() => setScanMode("fast")}
                disabled={busy}
              >
                Fast
              </button>
              <button
                type="button"
                className={`launch-segment-btn ${scanMode === "deep" ? "is-active" : ""}`}
                onClick={() => setScanMode("deep")}
                disabled={busy}
              >
                Deep
              </button>
            </div>
          </div>

          <div className="launch-control launch-control--toggle">
            <label className="launch-toggle">
              <input
                type="checkbox"
                checked={requiresLogin}
                onChange={(e) => setRequiresLogin(e.target.checked)}
                disabled={busy}
              />
              <span>Requires login</span>
            </label>
          </div>
        </div>

        {requiresLogin && (
          <div className="launch-auth-grid">
            <div className="launch-auth-field">
              <label className="launch-field-label" htmlFor="launch-user">
                Username
              </label>
              <input
                id="launch-user"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="user@company.com"
                autoComplete="username"
                disabled={busy}
              />
            </div>
            <div className="launch-auth-field">
              <label className="launch-field-label" htmlFor="launch-pass">
                Password
              </label>
              <input
                id="launch-pass"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                disabled={busy}
              />
            </div>
            <div className="launch-auth-field launch-auth-field--full">
              <label className="launch-field-label" htmlFor="launch-login-url">
                Login URL
              </label>
              <input
                id="launch-login-url"
                type="url"
                value={loginUrl}
                onChange={(e) => setLoginUrl(e.target.value)}
                placeholder={`Defaults to target URL (${url.trim() || "…"})`}
                autoComplete="off"
                disabled={busy}
              />
            </div>
          </div>
        )}

        <div className="launch-actions">
          <button
            type="button"
            className="btn-primary launch-btn"
            onClick={runScan}
            disabled={busy}
          >
            {busy ? "Launching…" : "Launch Scan →"}
          </button>
        </div>

        {busy && (
          <div className="scanning-indicator" aria-live="polite">
            Scanning<span className="dots" />
          </div>
        )}
        {msg && <p className="muted launch-msg">{msg}</p>}
        {busy && jobStatus === "WAITING_FOR_LOGIN" && <LoginWaitBanner />}
        {(busy || events.length > 0) && (
          <LiveScanLog
            events={events}
            targetUrl={url.trim()}
            scanTaskLabel={
              executionMode === "quick_action"
                ? `Quick: ${QUICK_ACTIONS.find((o) => o.value === microTask)?.label ?? microTask}`
                : isAdvancedMode
                  ? `Advanced (${advancedFlows.length} flows)`
                  : SCAN_TASK_PRESETS.find((o) => o.value === scanTask)?.label ?? scanTask
            }
            jobId={liveJobId}
            startedAtMs={scanStartedAt}
          />
        )}
      </div>

      <p className="launch-footer muted">
        <Link to="/history">View scan history</Link>
      </p>
    </div>
  );
}
