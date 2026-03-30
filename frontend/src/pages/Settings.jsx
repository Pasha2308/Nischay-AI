import { motion } from "framer-motion";
import { useState } from "react";
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
  return (
    <GlassCard className="p-5 grid gap-4">
      <div className="font-display font-bold text-lg">API Keys</div>
      <div className="glass px-3 py-2 flex items-center justify-between gap-3">
        <span className="font-mono" style={{ color: "var(--text-secondary)" }}>nai_••••••••••••••••</span>
        <button type="button" className="h-10 px-3 rounded-xl font-semibold" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}>
          Copy
        </button>
      </div>
      <div className="text-sm" style={{ color: "var(--warning)" }}>
        Regenerating will invalidate your current key.
      </div>
      <button type="button" className="h-11 px-4 rounded-xl font-semibold justify-self-start" style={{ background: "rgba(124,58,237,0.16)", color: "var(--accent-violet)", border: "1px solid rgba(124,58,237,0.35)" }}>
        Regenerate
      </button>
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

