import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { triggerTestRun } from "../services/backend-service";

const TASK_GROUPS = [
  { value: "quick_scan", label: "Quick scan" },
  { value: "conversion_scan", label: "Conversion scan" },
  { value: "full_app_scan", label: "Full app scan" },
] as const;

/** Mirrors backend `task_registry.TASK_REGISTRY` keys for advanced selection. */
const MICRO_TASK_OPTIONS: { id: string; label: string }[] = [
  { id: "login_user", label: "Login user" },
  { id: "search_product", label: "Search product" },
  { id: "open_product_from_search", label: "Open product from search" },
  { id: "add_to_cart", label: "Add to cart" },
  { id: "apply_coupon", label: "Apply coupon" },
  { id: "start_checkout", label: "Start checkout" },
  { id: "fill_address_form", label: "Fill address form" },
  { id: "place_order_attempt", label: "Place order attempt" },
  { id: "contact_support", label: "Contact support" },
  { id: "check_page_load", label: "Check page load" },
  { id: "check_navigation_links", label: "Check navigation links" },
];

function isValidHttpUrl(raw: string): boolean {
  const s = raw.trim();
  if (!s) return false;
  try {
    const u = new URL(s);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

export function TestPage() {
  const navigate = useNavigate();
  const [url, setUrl] = useState("");
  const [taskGroup, setTaskGroup] = useState<string>("full_app_scan");
  const [advanced, setAdvanced] = useState(false);
  const [selectedTasks, setSelectedTasks] = useState<string[]>([]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [browserType, setBrowserType] = useState<"chromium" | "firefox" | "webkit">("chromium");

  const toggleTask = (id: string) => {
    setSelectedTasks((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const handleStart = async () => {
    setError(null);
    const target = url.trim();
    if (!target) {
      setError("Enter a URL.");
      return;
    }
    if (!isValidHttpUrl(target)) {
      setError("Enter a valid URL starting with http:// or https://");
      return;
    }

    const em = email.trim();
    const hasFullCreds = Boolean(em && password);
    const partialCreds = Boolean(em || password);
    if (partialCreds && !hasFullCreds) {
      setError("Provide both email and password, or leave credentials empty.");
      return;
    }

    if (advanced && selectedTasks.length === 0) {
      setError("Select at least one micro task, or turn off Advanced mode.");
      return;
    }

    setBusy(true);
    try {
      const credentials = hasFullCreds
        ? { username: em, password, login_url: target }
        : undefined;

      const baseOptions = {
        scan_mode: "fast" as const,
        requires_login: hasFullCreds,
        credentials,
        browser_type: browserType,
      };

      const started = await triggerTestRun(
        target,
        advanced
          ? { ...baseOptions, flows: [...selectedTasks] }
          : { ...baseOptions, scan_task: taskGroup },
      );

      navigate(`/results/${started.job_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page launch-page test-page">
      <p className="job-results-back">
        <Link to="/">← Dashboard</Link>
      </p>

      <section className="launch-hero">
        <h1 className="launch-hero-title">Run a test</h1>
        <p className="launch-hero-subtitle">Start a scan and open results when the job is created</p>
      </section>

      <div className="launch-card card">
        <div className="launch-url-wrap">
          <label className="launch-field-label" htmlFor="test-url">
            URL
          </label>
          <input
            id="test-url"
            className="launch-url-input"
            type="url"
            inputMode="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com"
            disabled={busy}
            autoComplete="url"
            aria-invalid={error != null && error.includes("URL")}
          />
        </div>

        <div className="launch-control launch-control--wide" style={{ marginTop: 12 }}>
          <label className="launch-field-label" htmlFor="test-browser">
            Browser
          </label>
          <select
            id="test-browser"
            className="launch-select"
            value={browserType}
            onChange={(e) => setBrowserType(e.target.value as "chromium" | "firefox" | "webkit")}
            disabled={busy}
          >
            <option value="chromium">Chromium</option>
            <option value="firefox">Firefox</option>
            <option value="webkit">WebKit</option>
          </select>
        </div>

        <div className="launch-controls">
          <div className="launch-control launch-control--wide">
            <label className="launch-field-label" htmlFor="test-task-group">
              Task group
            </label>
            <select
              id="test-task-group"
              className="launch-select"
              value={taskGroup}
              onChange={(e) => setTaskGroup(e.target.value)}
              disabled={busy || advanced}
              aria-disabled={advanced}
            >
              {TASK_GROUPS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            {advanced ? (
              <p className="muted launch-micro-hint">Task group is ignored while Advanced mode selects individual tasks.</p>
            ) : null}

            <label className="launch-toggle launch-toggle--inline test-advanced-toggle">
              <input
                type="checkbox"
                checked={advanced}
                onChange={(e) => setAdvanced(e.target.checked)}
                disabled={busy}
              />
              <span>Advanced mode — pick micro tasks</span>
            </label>

            {advanced ? (
              <div className="test-micro-checklist" role="group" aria-label="Micro tasks to run">
                {MICRO_TASK_OPTIONS.map((t) => (
                  <label key={t.id} className="launch-adv-flow-chip test-micro-chip">
                    <input
                      type="checkbox"
                      checked={selectedTasks.includes(t.id)}
                      onChange={() => toggleTask(t.id)}
                      disabled={busy}
                    />
                    <span title={t.id}>{t.label}</span>
                  </label>
                ))}
              </div>
            ) : null}
          </div>
        </div>

        <div className="launch-auth-grid test-credentials">
          <div className="launch-auth-field">
            <label className="launch-field-label" htmlFor="test-email">
              Email <span className="muted">(optional)</span>
            </label>
            <input
              id="test-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              autoComplete="email"
              disabled={busy}
            />
          </div>
          <div className="launch-auth-field">
            <label className="launch-field-label" htmlFor="test-password">
              Password <span className="muted">(optional)</span>
            </label>
            <input
              id="test-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              disabled={busy}
            />
          </div>
        </div>

        <div className="launch-actions">
          <button
            type="button"
            className="btn-primary launch-btn"
            onClick={handleStart}
            disabled={busy}
            aria-busy={busy}
          >
            {busy ? "Starting…" : "Start test"}
          </button>
        </div>

        {busy ? (
          <div className="test-loading-indicator" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            <span>Starting job…</span>
          </div>
        ) : null}

        {error ? (
          <p className="launch-msg test-error" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
