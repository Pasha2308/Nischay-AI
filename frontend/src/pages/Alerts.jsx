import { motion } from "framer-motion";
import { Bell, Hash, Link as LinkIcon, Mail, ExternalLink } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { GlassCard } from "../components/ui/GlassCard";

export function Alerts() {
  const baseUrl = useMemo(() => {
    if (typeof window !== "undefined" && window.location && window.location.hostname) {
      const h = window.location.hostname;
      if (h === "localhost" || h === "127.0.0.1") return "http://localhost:8000";
    }
    return "https://api.nischay.ai";
  }, []);

  const [configs, setConfigs] = useState([]);
  const [history, setHistory] = useState([]);
  const [inApp, setInApp] = useState([]);
  const [open, setOpen] = useState(null); // { channel }
  const [rules, setRules] = useState({
    critical_enabled: true,
    critical_threshold: 80,
    failure_enabled: true,
  });

  async function refresh() {
    try {
      const c = await fetch(`${baseUrl}/alerts/config`).then((r) => r.json());
      setConfigs(Array.isArray(c) ? c : []);
    } catch {
      setConfigs([]);
    }
    try {
      const h = await fetch(`${baseUrl}/alerts/history`).then((r) => r.json());
      setHistory(Array.isArray(h) ? h : []);
    } catch {
      setHistory([]);
    }
    try {
      const n = await fetch(`${baseUrl}/notifications`).then((r) => r.json());
      setInApp(Array.isArray(n) ? n : []);
    } catch {
      setInApp([]);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseUrl]);

  const byChannel = useMemo(() => {
    const map = {};
    for (const c of configs) map[c.channel] = c;
    return map;
  }, [configs]);

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: "easeOut" }} className="grid gap-6 md:ml-[240px]">
      <div className="font-display text-2xl font-extrabold">Alerts</div>

      <div className="grid gap-4 md:grid-cols-2">
        <Channel
          icon={Mail}
          title="Email"
          status={
            byChannel.email?.config?.recipients?.length
              ? `Configured (${byChannel.email.config.recipients.length} recipients)`
              : "Not configured"
          }
          action="Configure"
          onClick={() => setOpen({ channel: "email" })}
        />
        <Channel
          icon={Hash}
          title="Slack"
          status={
            byChannel.slack?.config?.channel
              ? `Connected to ${byChannel.slack.config.channel}`
              : byChannel.slack?.config?.webhook_url
              ? "Connected"
              : "Not connected"
          }
          action={byChannel.slack?.config?.webhook_url ? "Configure" : "Connect to Slack"}
          onClick={() => setOpen({ channel: "slack" })}
        />
        <Channel
          icon={LinkIcon}
          title="Webhook"
          status={byChannel.webhook?.config?.url ? `Active (${byChannel.webhook.config.url})` : "Not configured"}
          action="Configure"
          onClick={() => setOpen({ channel: "webhook" })}
        />
        <Channel icon={Bell} title="In-app" status="Enabled" action="Manage" onClick={() => setOpen({ channel: "in_app" })} />
      </div>

      <GlassCard className="p-5">
        <div className="font-display font-bold text-lg">Alert Rules</div>
        <div className="mt-3 grid gap-2 text-sm" style={{ color: "var(--text-secondary)" }}>
          <div className="glass px-3 py-2 flex items-center justify-between gap-3">
            <div className="grid">
              <span className="font-semibold">Critical Alert</span>
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                Fires when risk_score exceeds threshold
              </span>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="number"
                value={rules.critical_threshold}
                onChange={(e) => setRules((p) => ({ ...p, critical_threshold: Number(e.target.value) || 80 }))}
                className="h-10 w-20 rounded-xl px-3 outline-none font-mono"
                style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-primary)" }}
              />
              <button
                type="button"
                onClick={() => setRules((p) => ({ ...p, critical_enabled: !p.critical_enabled }))}
                className="h-10 px-3 rounded-xl font-semibold"
                style={{ background: rules.critical_enabled ? "rgba(0,212,255,0.14)" : "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: rules.critical_enabled ? "var(--accent-cyan)" : "var(--text-secondary)" }}
              >
                {rules.critical_enabled ? "Enabled" : "Disabled"}
              </button>
            </div>
          </div>
          <div className="glass px-3 py-2 flex items-center justify-between gap-3">
            <div className="grid">
              <span className="font-semibold">Failure Alert</span>
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                Fires when scan run fails
              </span>
            </div>
            <button
              type="button"
              onClick={() => setRules((p) => ({ ...p, failure_enabled: !p.failure_enabled }))}
              className="h-10 px-3 rounded-xl font-semibold"
              style={{ background: rules.failure_enabled ? "rgba(0,212,255,0.14)" : "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: rules.failure_enabled ? "var(--accent-cyan)" : "var(--text-secondary)" }}
            >
              {rules.failure_enabled ? "Enabled" : "Disabled"}
            </button>
          </div>
          <div className="flex justify-end gap-2 mt-2">
            <button
              type="button"
              onClick={async () => {
                // Apply the same trigger rules to all configured channels (simple global rules).
                const next = {
                  risk_score_above: rules.critical_enabled ? rules.critical_threshold : null,
                  on_critical_defect: true,
                  on_run_complete: false,
                };
                for (const ch of ["email", "slack", "webhook", "in_app"]) {
                  const existing = byChannel[ch] || { channel: ch, is_enabled: ch === "in_app", config: {}, trigger_rules: {} };
                  await fetch(`${baseUrl}/alerts/config`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      channel: ch,
                      is_enabled: existing.is_enabled ?? (ch === "in_app"),
                      config: existing.config || {},
                      trigger_rules: next,
                    }),
                  });
                }
                refresh();
              }}
              className="h-10 px-3 rounded-xl font-semibold"
              style={{ background: "rgba(0,212,255,0.14)", color: "var(--accent-cyan)", border: "1px solid rgba(0,212,255,0.35)" }}
            >
              Save Rules
            </button>
          </div>
        </div>
      </GlassCard>

      <GlassCard className="p-5">
        <div className="font-display font-bold text-lg">Notification history</div>
        <div className="mt-3 grid gap-2">
          {history.length ? (
            history.map((h) => (
              <div key={h.id} className="glass px-3 py-2 flex items-center justify-between gap-3">
                <div className="grid">
                  <div className="text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>
                    {h.channel} · {h.status}
                  </div>
                  <div className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                    {h.timestamp || "—"} · {h.scan_url || "—"} · {h.reason || "—"}
                  </div>
                </div>
                {h.scan_id ? (
                  <a
                    href={`/results/${h.scan_id}`}
                    className="h-9 px-3 rounded-xl font-semibold inline-flex items-center gap-2"
                    style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}
                  >
                    View <ExternalLink size={14} />
                  </a>
                ) : null}
              </div>
            ))
          ) : (
            <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
              No alerts sent yet.
            </div>
          )}
        </div>
      </GlassCard>

      {open ? (
        <ConfigModal
          baseUrl={baseUrl}
          channel={open.channel}
          existing={byChannel[open.channel] || null}
          inApp={inApp}
          onClose={() => setOpen(null)}
          onSaved={() => {
            setOpen(null);
            refresh();
          }}
        />
      ) : null}
    </motion.div>
  );
}

function Channel({ icon: Icon, title, status, action, onClick }) {
  return (
    <GlassCard className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl grid place-items-center" style={{ background: "rgba(0,212,255,0.12)", border: "1px solid rgba(48,54,61,0.65)", color: "var(--accent-cyan)" }}>
            <Icon size={18} />
          </div>
          <div>
            <div className="font-display font-bold">{title}</div>
            <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
              {status}
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={onClick}
          className="h-10 px-3 rounded-xl font-semibold"
          style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}
        >
          {action}
        </button>
      </div>
    </GlassCard>
  );
}

function ConfigModal({ baseUrl, channel, existing, inApp, onClose, onSaved }) {
  const [enabled, setEnabled] = useState(Boolean(existing?.is_enabled ?? (channel === "in_app")));
  const [statusMsg, setStatusMsg] = useState("");
  const [riskAbove, setRiskAbove] = useState(existing?.trigger_rules?.risk_score_above ?? 70);
  const [onCritical, setOnCritical] = useState(Boolean(existing?.trigger_rules?.on_critical_defect ?? true));
  const [onComplete, setOnComplete] = useState(Boolean(existing?.trigger_rules?.on_run_complete ?? false));

  const [emailRecips, setEmailRecips] = useState((existing?.config?.recipients || []).join(", "));
  const [slackWebhook, setSlackWebhook] = useState(existing?.config?.webhook_url || "");
  const [slackChannel, setSlackChannel] = useState(existing?.config?.channel || "");
  const [webhookUrl, setWebhookUrl] = useState(existing?.config?.url || "");
  const [webhookSecret, setWebhookSecret] = useState(existing?.config?.secret || "");

  const title =
    channel === "email"
      ? "Configure Email"
      : channel === "slack"
      ? "Connect Slack"
      : channel === "webhook"
      ? "Configure Webhook"
      : "In-app notifications";

  async function save() {
    setStatusMsg("");
    const config =
      channel === "email"
        ? { recipients: emailRecips.split(",").map((x) => x.trim()).filter(Boolean) }
        : channel === "slack"
        ? { webhook_url: slackWebhook.trim(), channel: slackChannel.trim() }
        : channel === "webhook"
        ? { url: webhookUrl.trim(), secret: webhookSecret.trim() }
        : {};
    const trigger_rules = {
      risk_score_above: Number(riskAbove) || 70,
      on_critical_defect: Boolean(onCritical),
      on_run_complete: Boolean(onComplete),
    };
    const res = await fetch(`${baseUrl}/alerts/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel, is_enabled: enabled, config, trigger_rules }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setStatusMsg(`❌ Failed: ${data?.detail || "Could not save"}`);
      return;
    }
    onSaved?.();
  }

  async function test() {
    setStatusMsg("Testing…");
    const res = await fetch(`${baseUrl}/alerts/test/${channel}`, { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data?.success) setStatusMsg(`✅ ${data.message || "Test sent"}`);
    else setStatusMsg(`❌ Failed: ${data?.message || data?.detail || "Test failed"}`);
  }

  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0" style={{ background: "rgba(10,12,16,0.65)", backdropFilter: "blur(6px)" }} onClick={onClose} />
      <div className="absolute left-1/2 top-1/2 w-[min(760px,92vw)] -translate-x-1/2 -translate-y-1/2 glass p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="font-display text-xl font-bold">{title}</div>
          <button type="button" onClick={onClose} className="h-10 px-3 rounded-xl font-semibold" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}>
            Close
          </button>
        </div>

        {channel === "in_app" ? (
          <div className="mt-4 grid gap-2">
            {inApp.length ? (
              inApp.slice(0, 20).map((n) => (
                <div key={n.id} className="glass px-3 py-2">
                  <div className="text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>{n.title}</div>
                  <div className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>{n.created_at || "—"} · {n.payload?.url || "—"} · risk {n.payload?.risk_score ?? "—"}</div>
                  {n.payload?.scan_id ? <a href={`/results/${n.payload.scan_id}`} style={{ color: "var(--accent-cyan)" }} className="text-xs inline-flex items-center gap-2 mt-1">View <ExternalLink size={14} /></a> : null}
                </div>
              ))
            ) : (
              <div className="text-sm" style={{ color: "var(--text-secondary)" }}>No in-app notifications yet.</div>
            )}
          </div>
        ) : (
          <>
            <div className="mt-4 grid gap-3">
              <label className="glass px-3 py-2 rounded-xl">
                <div className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>Enabled</div>
                <div className="mt-2">
                  <input type="checkbox" checked={enabled} onChange={() => setEnabled((v) => !v)} />
                </div>
              </label>

              {channel === "email" ? (
                <label className="grid gap-2">
                  <span className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>Recipients</span>
                  <input value={emailRecips} onChange={(e) => setEmailRecips(e.target.value)} placeholder="a@b.com, c@d.com" className="h-11 rounded-xl px-3 outline-none" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }} />
                </label>
              ) : null}

              {channel === "slack" ? (
                <>
                  <label className="grid gap-2">
                    <span className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>Webhook URL</span>
                    <input value={slackWebhook} onChange={(e) => setSlackWebhook(e.target.value)} placeholder="https://hooks.slack.com/..." className="h-11 rounded-xl px-3 outline-none" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }} />
                    <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
                      Create an incoming webhook at{" "}
                      <a href="https://api.slack.com/apps" target="_blank" rel="noreferrer" style={{ color: "var(--accent-cyan)" }}>
                        api.slack.com/apps
                      </a>
                    </div>
                  </label>
                  <label className="grid gap-2">
                    <span className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>Channel (optional)</span>
                    <input value={slackChannel} onChange={(e) => setSlackChannel(e.target.value)} placeholder="#qa-alerts" className="h-11 rounded-xl px-3 outline-none" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }} />
                  </label>
                </>
              ) : null}

              {channel === "webhook" ? (
                <>
                  <label className="grid gap-2">
                    <span className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>Endpoint URL</span>
                    <input value={webhookUrl} onChange={(e) => setWebhookUrl(e.target.value)} placeholder="https://your-site.com/hook" className="h-11 rounded-xl px-3 outline-none" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }} />
                  </label>
                  <label className="grid gap-2">
                    <span className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>Secret (optional)</span>
                    <input value={webhookSecret} onChange={(e) => setWebhookSecret(e.target.value)} placeholder="optional" className="h-11 rounded-xl px-3 outline-none" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }} />
                  </label>
                  <details className="glass px-3 py-2 rounded-xl">
                    <summary className="text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>Payload preview</summary>
                    <pre className="mt-2 text-xs overflow-auto" style={{ color: "var(--text-muted)" }}>{`{ "scan_id": "...", "target_url": "...", "risk_score": 87, "issues": [ ... ] }`}</pre>
                  </details>
                </>
              ) : null}

              <div className="glass px-3 py-2 rounded-xl">
                <div className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>Trigger rules</div>
                <div className="mt-2 grid gap-2 text-sm" style={{ color: "var(--text-secondary)" }}>
                  <label className="flex items-center justify-between gap-3">
                    <span>Send when risk score exceeds:</span>
                    <input type="number" value={riskAbove} onChange={(e) => setRiskAbove(Number(e.target.value) || 70)} className="h-9 w-20 rounded-xl px-3 outline-none font-mono" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-primary)" }} />
                  </label>
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={onCritical} onChange={() => setOnCritical((v) => !v)} />
                    <span>Send when critical defect found</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={onComplete} onChange={() => setOnComplete((v) => !v)} />
                    <span>Send on every scan completion</span>
                  </label>
                </div>
              </div>

              {statusMsg ? <div className="text-sm" style={{ color: statusMsg.startsWith("✅") ? "var(--success)" : "var(--warning)" }}>{statusMsg}</div> : null}
              <div className="flex justify-end gap-2">
                <button type="button" onClick={test} className="h-11 px-4 rounded-xl font-semibold" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}>
                  Send test {channel === "email" ? "email" : channel === "slack" ? "message" : "webhook"}
                </button>
                <button type="button" onClick={save} className="h-11 px-4 rounded-xl font-semibold" style={{ background: "linear-gradient(135deg, #00D4FF, #7C3AED)", color: "#0A0C10" }}>
                  Save
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

