import { motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { GlassCard } from "../components/ui/GlassCard";
import { ToggleSwitch } from "../components/ui/ToggleSwitch";

export function Settings() {
  const [tab, setTab] = useState("Profile");
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: "easeOut" }} className="grid gap-6 md:ml-[240px]">
      <div className="font-display text-2xl font-extrabold">Settings</div>

      <GlassCard className="p-4 flex flex-wrap gap-2">
        {["Profile", "Team", "Preferences", "API Keys", "About"].map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className="h-10 px-3 rounded-xl text-sm font-semibold"
            style={{
              background: tab === t ? "rgba(0,212,255,0.14)" : "rgba(22,27,34,0.75)",
              color: tab === t ? "var(--accent-cyan)" : "var(--text-secondary)",
              border: "1px solid rgba(48,54,61,0.7)",
            }}
          >
            {t}
          </button>
        ))}
      </GlassCard>

      {tab === "Profile" ? <Profile /> : null}
      {tab === "Team" ? <Team /> : null}
      {tab === "Preferences" ? <Prefs /> : null}
      {tab === "API Keys" ? <ApiKeys /> : null}
      {tab === "About" ? <About /> : null}
    </motion.div>
  );
}

function Profile() {
  return (
    <GlassCard className="p-5 grid gap-4">
      <div className="flex items-center gap-3">
        <div className="h-12 w-12 rounded-full grid place-items-center font-semibold" style={{ background: "rgba(0,212,255,0.18)", border: "1px solid rgba(48,54,61,0.7)" }}>
          NA
        </div>
        <div>
          <div className="font-display font-bold">Nischay Analyst</div>
          <div className="text-sm" style={{ color: "var(--text-secondary)" }}>Operations</div>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <Field label="Display Name" value="Nischay Analyst" />
        <Field label="Email" value="analyst@nischay.ai" />
        <Field label="Organization" value="Nischay Labs" />
      </div>
      <button type="button" className="h-11 px-4 rounded-xl font-semibold justify-self-start" style={{ background: "rgba(0,212,255,0.14)", color: "var(--accent-cyan)", border: "1px solid rgba(0,212,255,0.35)" }}>
        Save Changes
      </button>
    </GlassCard>
  );
}

function Team() {
  return (
    <GlassCard className="p-5 grid gap-4">
      <div className="font-display font-bold text-lg">Team</div>
      <div className="grid gap-3 md:grid-cols-[1fr_auto]">
        <input placeholder="Invite member email" className="h-11 rounded-xl px-3 outline-none" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }} />
        <button type="button" className="h-11 px-4 rounded-xl font-semibold" style={{ background: "rgba(0,212,255,0.14)", color: "var(--accent-cyan)", border: "1px solid rgba(0,212,255,0.35)" }}>
          Send Invite
        </button>
      </div>
      <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
        Members (demo)
      </div>
    </GlassCard>
  );
}

function Prefs() {
  const [retry, setRetry] = useState(true);
  return (
    <GlassCard className="p-5 grid gap-4">
      <div className="font-display font-bold text-lg">Preferences</div>
      <ToggleSwitch checked={retry} onChange={setRetry} label="Auto-run on schedule failure retry" />
      <button type="button" className="h-11 px-4 rounded-xl font-semibold justify-self-start" style={{ background: "rgba(0,212,255,0.14)", color: "var(--accent-cyan)", border: "1px solid rgba(0,212,255,0.35)" }}>
        Save Preferences
      </button>
    </GlassCard>
  );
}

function ApiKeys() {
  const baseUrl = useMemo(() => {
    if (typeof window !== "undefined" && window.location && window.location.hostname) {
      const h = window.location.hostname;
      if (h === "localhost" || h === "127.0.0.1") return "http://localhost:8000";
    }
    return "https://api.nischay.ai";
  }, []);
  const [keys, setKeys] = useState([]);
  const [modal, setModal] = useState(null);
  const [llmProvider, setLlmProvider] = useState("groq");
  const [llmModels, setLlmModels] = useState([]);
  const [llmModel, setLlmModel] = useState("");
  const [llmKey, setLlmKey] = useState("");
  const [llmKeyShown, setLlmKeyShown] = useState(false);
  const [llmStatus, setLlmStatus] = useState({ kind: "", message: "" });
  const [llmCurrent, setLlmCurrent] = useState(null);
  const [analyticsSummary, setAnalyticsSummary] = useState(null);

  async function refresh() {
    try {
      const res = await fetch(`${baseUrl}/api-keys`);
      const data = await res.json();
      setKeys(Array.isArray(data) ? data : []);
    } catch {
      setKeys([]);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseUrl]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cur = await fetch(`${baseUrl}/settings/llm`).then((r) => r.json());
        if (!cancelled) setLlmCurrent(cur && typeof cur === "object" ? cur : null);
      } catch {
        if (!cancelled) setLlmCurrent(null);
      }
      try {
        const s = await fetch(`${baseUrl}/analytics/summary`).then((r) => r.json());
        if (!cancelled) setAnalyticsSummary(s && typeof s === "object" ? s : null);
      } catch {
        if (!cancelled) setAnalyticsSummary(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [baseUrl]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await fetch(`${baseUrl}/settings/llm/models?provider=${encodeURIComponent(llmProvider)}`).then((r) => r.json());
        if (cancelled) return;
        setLlmModels(Array.isArray(data) ? data : []);
        const rec = (Array.isArray(data) ? data : []).find((m) => m.recommended);
        setLlmModel((prev) => prev || rec?.id || (data?.[0]?.id ?? ""));
      } catch {
        if (cancelled) return;
        setLlmModels([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [baseUrl, llmProvider]);

  return (
    <GlassCard className="p-5 grid gap-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="font-display font-bold text-lg">API Keys</div>
          <div className="text-sm mt-2" style={{ color: "var(--text-secondary)" }}>
            Use these keys for REST API and CI/CD integrations.
          </div>
        </div>
        <button
          type="button"
          onClick={async () => {
            const res = await fetch(`${baseUrl}/api-keys`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ name: "Settings Key" }),
            });
            const data = await res.json();
            if (res.ok && data?.api_key) {
              setModal({ apiKey: data.api_key });
              refresh();
            } else {
              setModal({ error: data?.detail || "Failed to generate key" });
            }
          }}
          className="h-11 px-4 rounded-xl font-semibold"
          style={{ background: "rgba(0,212,255,0.14)", color: "var(--accent-cyan)", border: "1px solid rgba(0,212,255,0.35)" }}
        >
          Generate API Key
        </button>
      </div>

      <div className="grid gap-2">
        {keys.length ? (
          keys.map((k) => (
            <div key={k.id} className="glass px-3 py-2 flex items-center justify-between gap-3">
              <div className="grid">
                <div className="font-display font-bold">{k.name}</div>
                <div className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                  {k.key_prefix} · created {k.created_at ? new Date(k.created_at).toLocaleString() : "—"} · last used{" "}
                  {k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "—"}
                </div>
              </div>
              <button
                type="button"
                onClick={async () => {
                  await fetch(`${baseUrl}/api-keys/${k.id}`, { method: "DELETE" });
                  refresh();
                }}
                className="h-9 px-3 rounded-xl font-semibold"
                style={{ background: "rgba(124,58,237,0.16)", color: "var(--accent-violet)", border: "1px solid rgba(124,58,237,0.35)" }}
              >
                Revoke
              </button>
            </div>
          ))
        ) : (
          <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
            No API keys yet.
          </div>
        )}
      </div>

      {modal ? (
        <div className="fixed inset-0 z-50">
          <div className="absolute inset-0" style={{ background: "rgba(10,12,16,0.65)", backdropFilter: "blur(6px)" }} onClick={() => setModal(null)} />
          <div className="absolute left-1/2 top-1/2 w-[min(640px,92vw)] -translate-x-1/2 -translate-y-1/2 glass p-5">
            <div className="font-display text-xl font-bold">API Key</div>
            {modal.apiKey ? (
              <>
                <div className="mt-3 text-sm" style={{ color: "var(--warning)" }}>
                  Copy this key now. It will never be shown again.
                </div>
                <div className="mt-3 glass px-3 py-2 flex items-center justify-between gap-3">
                  <span className="font-mono text-sm" style={{ color: "var(--text-secondary)" }}>{modal.apiKey}</span>
                  <button
                    type="button"
                    onClick={() => navigator.clipboard.writeText(modal.apiKey)}
                    className="h-10 px-3 rounded-xl font-semibold"
                    style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}
                  >
                    Copy
                  </button>
                </div>
              </>
            ) : (
              <div className="mt-3 text-sm" style={{ color: "var(--warning)" }}>
                {modal.error || "Could not generate key."}
              </div>
            )}
            <button
              type="button"
              onClick={() => setModal(null)}
              className="mt-4 h-11 w-full rounded-xl font-semibold"
              style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}
            >
              Close
            </button>
          </div>
        </div>
      ) : null}

      <div className="h-px" style={{ background: "rgba(48,54,61,0.65)" }} />

      <div className="grid gap-3">
        <div>
          <div className="font-display font-bold text-lg">LLM Configuration</div>
          <div className="text-sm mt-2" style={{ color: "var(--text-secondary)" }}>
            Bring your own LLM key. Changes apply on the next scan without restart.
          </div>
        </div>

        {llmCurrent && llmCurrent.provider ? (
          <div className="glass px-3 py-2 flex items-center justify-between gap-3">
            <div className="font-mono text-xs" style={{ color: "var(--text-secondary)" }}>
              ● {String(llmCurrent.provider).toUpperCase()} &nbsp; {llmCurrent.model_name} &nbsp; {llmCurrent.key_masked}
              {llmCurrent.verified_at ? ` · Verified ${new Date(llmCurrent.verified_at).toLocaleString()}` : ""}
            </div>
            <button
              type="button"
              onClick={() => {
                setLlmProvider(String(llmCurrent.provider || "groq"));
                setLlmModel(String(llmCurrent.model_name || ""));
              }}
              className="h-9 px-3 rounded-xl font-semibold"
              style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}
            >
              Update
            </button>
          </div>
        ) : null}

        <div className="grid gap-2 md:grid-cols-3">
          {[
            { id: "groq", title: "🟢 Groq", sub: "Free tier" },
            { id: "openai", title: "OpenAI", sub: "Paid" },
            { id: "anthropic", title: "Anthropic", sub: "Paid" },
          ].map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setLlmProvider(p.id)}
              className="glass p-4 rounded-xl text-left"
              style={{
                border: llmProvider === p.id ? "1px solid rgba(0,212,255,0.55)" : "1px solid rgba(48,54,61,0.7)",
                boxShadow: llmProvider === p.id ? "0 0 24px rgba(0,212,255,0.12)" : "none",
              }}
            >
              <div className="font-display font-bold">{p.title}</div>
              <div className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
                {p.sub}
              </div>
            </button>
          ))}
        </div>

        <label className="grid gap-2">
          <span className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
            API Key
          </span>
          <div className="grid gap-2 md:grid-cols-[1fr_auto]">
            <input
              value={llmKey}
              onChange={(e) => setLlmKey(e.target.value)}
              type={llmKeyShown ? "text" : "password"}
              placeholder={llmCurrent?.key_masked ? llmCurrent.key_masked : "Enter your API key"}
              className="h-11 rounded-xl px-3 outline-none"
              style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }}
            />
            <button
              type="button"
              onClick={() => setLlmKeyShown((v) => !v)}
              className="h-11 px-4 rounded-xl font-semibold"
              style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}
            >
              {llmKeyShown ? "Hide" : "Show"}
            </button>
          </div>
          <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
            {llmProvider === "groq" ? (
              <>
                Get your free key at{" "}
                <a href="https://console.groq.com" target="_blank" rel="noreferrer" style={{ color: "var(--accent-cyan)" }}>
                  console.groq.com →
                </a>
              </>
            ) : llmProvider === "openai" ? (
              <>
                Get your key at{" "}
                <a href="https://platform.openai.com" target="_blank" rel="noreferrer" style={{ color: "var(--accent-cyan)" }}>
                  platform.openai.com →
                </a>
              </>
            ) : (
              <>
                Get your key at{" "}
                <a href="https://console.anthropic.com" target="_blank" rel="noreferrer" style={{ color: "var(--accent-cyan)" }}>
                  console.anthropic.com →
                </a>
              </>
            )}
          </div>
        </label>

        <label className="grid gap-2">
          <span className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
            Model
          </span>
          <select
            value={llmModel}
            onChange={(e) => setLlmModel(e.target.value)}
            className="h-11 rounded-xl px-3 outline-none"
            style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-primary)" }}
          >
            {llmModels.map((m) => (
              <option key={m.id} value={m.id}>
                {m.recommended ? "⭐ " : ""}{m.label} · {m.speed} · {m.tier}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          onClick={async () => {
            setLlmStatus({ kind: "loading", message: "Verifying key…" });
            try {
              const res = await fetch(`${baseUrl}/settings/llm`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ provider: llmProvider, api_key: llmKey.trim(), model_name: llmModel }),
              });
              const data = await res.json().catch(() => ({}));
              if (!res.ok) {
                setLlmStatus({ kind: "error", message: data?.detail || "Failed to save config" });
                return;
              }
              if (data?.verified) {
                setLlmStatus({ kind: "success", message: `Key verified — ${llmModel} is ready` });
              } else {
                setLlmStatus({ kind: "error", message: data?.error || "Key saved but verification failed" });
              }
              try {
                const cur = await fetch(`${baseUrl}/settings/llm`).then((r) => r.json());
                setLlmCurrent(cur && typeof cur === "object" ? cur : null);
              } catch {
                setLlmCurrent(null);
              }
            } catch (e) {
              setLlmStatus({ kind: "error", message: String(e?.message || e) });
            }
          }}
          className="h-11 px-4 rounded-xl font-semibold justify-self-start"
          style={{ background: "linear-gradient(135deg, #00D4FF, #7C3AED)", color: "#0A0C10" }}
        >
          Save &amp; Verify
        </button>

        {llmStatus.message ? (
          <div className="text-sm" style={{ color: llmStatus.kind === "success" ? "var(--success)" : llmStatus.kind === "loading" ? "var(--text-secondary)" : "var(--warning)" }}>
            {llmStatus.kind === "success" ? "✅ " : llmStatus.kind === "error" ? "❌ " : ""}{llmStatus.message}
          </div>
        ) : null}

        <div className="glass px-3 py-2">
          <div className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
            Usage
          </div>
          <div className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
            ~{Math.max(0, Number(analyticsSummary?.total_scans || 0) * 5)} LLM calls this month
          </div>
        </div>
      </div>
    </GlassCard>
  );
}

function About() {
  return (
    <GlassCard className="p-5 grid gap-3 place-items-center text-center">
      <div className="font-display text-3xl font-extrabold">Nischay AI</div>
      <div className="text-sm" style={{ color: "var(--text-secondary)" }}>Autonomous QA Intelligence Platform</div>
      <div className="text-sm" style={{ color: "var(--text-secondary)" }}>Version 1.0.0</div>
      <div className="text-sm" style={{ color: "var(--text-secondary)" }}>Built with Python, FastAPI, Playwright, React</div>
    </GlassCard>
  );
}

function Field({ label, value }) {
  return (
    <label className="grid gap-2 text-sm" style={{ color: "var(--text-secondary)" }}>
      <span className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>{label}</span>
      <input defaultValue={value} className="h-11 rounded-xl px-3 outline-none" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-primary)" }} />
    </label>
  );
}

