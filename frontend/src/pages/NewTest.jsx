import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import { Globe, Rocket, Search, Shield, Zap, Check } from "lucide-react";
import { GlassCard } from "../components/ui/GlassCard";
import { ToggleSwitch } from "../components/ui/ToggleSwitch";
import { useToast } from "../hooks/useToast";
import { API } from "../config/api";
import { useNavigate } from "react-router-dom";

const MODULES = [
  "auth",
  "navigation",
  "search",
  "product_pages",
  "cart",
  "checkout",
  "wishlist",
  "performance",
  "accessibility",
  "security",
  "links_assets",
];

function isValidUrl(u) {
  try {
    const x = new URL(u);
    return x.protocol === "http:" || x.protocol === "https:";
  } catch {
    return false;
  }
}

export function NewTest() {
  const toast = useToast();
  const nav = useNavigate();

  const [currentStep, setCurrentStep] = useState(1);
  const [url, setUrl] = useState("https://your-ecommerce-store.com");
  const [depth, setDepth] = useState("standard");
  const [modules, setModules] = useState(["auth", "cart"]);
  const [tasksText, setTasksText] = useState("test login\nsearch for a product\nadd to cart and proceed to checkout");
  const [device, setDevice] = useState("desktop");
  const [authOn, setAuthOn] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [progressMsg, setProgressMsg] = useState("");

  const okUrl = isValidUrl(url);
  const tasks = useMemo(
    () =>
      tasksText
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
    [tasksText],
  );

  const body = useMemo(
    () => ({
      url,
      depth,
      modules,
      tasks,
      device,
      auth: authOn ? { email, password } : undefined,
    }),
    [url, depth, modules, tasks, device, authOn, email, password],
  );

  function toggleModule(m) {
    setModules((prev) => (prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]));
  }

  async function onLaunch() {
    if (!okUrl) {
      toast.error("Please enter a valid URL.");
      return;
    }
    setIsLoading(true);
    const msgs = [
      "Crawling pages…",
      "Planning test actions…",
      "Executing tests…",
      "Detecting issues…",
      "Calculating risk score…",
      "Generating report…",
    ];
    let i = 0;
    setProgressMsg(msgs[i]);
    const timer = window.setInterval(() => {
      i = (i + 1) % msgs.length;
      setProgressMsg(msgs[i]);
    }, 900);
    try {
      const res = await fetch(API.runTest, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = res.ok ? await res.json().catch(() => null) : null;
      const rid = data?.run_id ?? data?.job_id ?? data?.id;
      if (!res.ok || !rid) {
        throw new Error("bad response");
      }
      toast.success("QA test launched.");
      nav(`/live/${encodeURIComponent(String(rid))}`);
    } catch {
      toast.error("Unable to start run. Check the API URL and try again.");
    } finally {
      window.clearInterval(timer);
      setIsLoading(false);
      setProgressMsg("");
    }
  }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: "easeOut" }} className="grid gap-6 md:ml-[240px]">
      <StepHeader current={currentStep} onStep={setCurrentStep} />

      {currentStep === 1 ? (
        <GlassCard className="p-6 grid gap-5">
          <div className="font-display text-xl font-bold">Configure</div>
          <div className="grid gap-2">
            <label className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
              Target URL
            </label>
            <div className="relative">
              <Globe size={16} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--text-secondary)" }} />
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://your-ecommerce-store.com"
                className="w-full h-12 pl-10 pr-10 rounded-xl outline-none"
                style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }}
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2">
                {okUrl ? <Check size={16} style={{ color: "var(--success)" }} /> : <span style={{ color: "var(--danger)" }}>×</span>}
              </span>
            </div>
          </div>

          <div className="grid gap-2">
            <div className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
              Test Depth
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <DepthCard
                title="Quick Scan"
                icon={Zap}
                meta="~1 minute"
                desc="Surface-level check"
                active={depth === "quick"}
                onClick={() => setDepth("quick")}
              />
              <DepthCard
                title="Standard"
                icon={Shield}
                meta="~3 minutes"
                desc="Full page coverage"
                active={depth === "standard"}
                onClick={() => setDepth("standard")}
              />
              <DepthCard
                title="Deep Scan"
                icon={Search}
                meta="~8 minutes"
                desc="Complete QA suite"
                active={depth === "deep"}
                onClick={() => setDepth("deep")}
              />
            </div>
          </div>

          <div className="grid gap-2">
            <div className="flex items-center justify-between gap-3">
              <div className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
                Modules
              </div>
              <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
                <button type="button" onClick={() => setModules(MODULES)} style={{ color: "var(--accent-cyan)" }}>
                  Select All
                </button>{" "}
                ·{" "}
                <button type="button" onClick={() => setModules([])} style={{ color: "var(--accent-cyan)" }}>
                  Clear
                </button>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {MODULES.map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => toggleModule(m)}
                  className="px-3 py-2 rounded-full text-sm"
                  style={{
                    background: modules.includes(m) ? "rgba(0,212,255,0.20)" : "rgba(22,27,34,0.75)",
                    color: modules.includes(m) ? "#0A0C10" : "var(--text-secondary)",
                    border: "1px solid rgba(48,54,61,0.7)",
                  }}
                >
                  {m.replaceAll("_", " ")}
                </button>
              ))}
            </div>
          </div>

          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => setCurrentStep(2)}
              className="h-11 px-4 rounded-xl font-semibold"
              style={{ background: "rgba(0,212,255,0.14)", color: "var(--accent-cyan)", border: "1px solid rgba(0,212,255,0.35)" }}
            >
              Continue →
            </button>
          </div>
        </GlassCard>
      ) : null}

      {currentStep === 2 ? (
        <GlassCard className="p-6 grid gap-5">
          <div className="font-display text-xl font-bold">Options</div>

          <div className="grid gap-2">
            <div className="flex items-center justify-between gap-3">
              <label className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
                Tasks
              </label>
              <div className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                {tasksText.length} chars
              </div>
            </div>
            <textarea
              value={tasksText}
              onChange={(e) => setTasksText(e.target.value)}
              rows={5}
              className="w-full rounded-xl p-3 outline-none"
              style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-primary)" }}
              placeholder="Describe what to test in plain English…"
            />
            <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
              Nischay AI converts your description into test steps.
            </div>
          </div>

          <div className="grid gap-2">
            <div className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
              Device
            </div>
            <div className="grid grid-cols-3 gap-2">
              <DeviceButton label="Desktop" active={device === "desktop"} onClick={() => setDevice("desktop")} />
              <DeviceButton label="Mobile" active={device === "mobile"} onClick={() => setDevice("mobile")} />
              <DeviceButton label="Tablet" active={device === "tablet"} onClick={() => setDevice("tablet")} />
            </div>
          </div>

          <GlassCard className="p-4 grid gap-3">
            <ToggleSwitch checked={authOn} onChange={setAuthOn} label="Test behind login?" />
            {authOn ? (
              <div className="grid gap-3 md:grid-cols-2">
                <input
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Email"
                  className="h-11 rounded-xl px-3 outline-none"
                  style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }}
                />
                <input
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Password"
                  type="password"
                  className="h-11 rounded-xl px-3 outline-none"
                  style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }}
                />
              </div>
            ) : null}
          </GlassCard>

          <div className="flex justify-between gap-3">
            <button
              type="button"
              onClick={() => setCurrentStep(1)}
              className="h-11 px-4 rounded-xl font-semibold"
              style={{ background: "rgba(22,27,34,0.75)", color: "var(--text-secondary)", border: "1px solid rgba(48,54,61,0.7)" }}
            >
              ← Back
            </button>
            <button
              type="button"
              onClick={() => setCurrentStep(3)}
              className="h-11 px-4 rounded-xl font-semibold"
              style={{ background: "rgba(0,212,255,0.14)", color: "var(--accent-cyan)", border: "1px solid rgba(0,212,255,0.35)" }}
            >
              Continue →
            </button>
          </div>
        </GlassCard>
      ) : null}

      {currentStep === 3 ? (
        <GlassCard className="p-6 grid gap-5">
          <div className="font-display text-xl font-bold">Launch</div>

          <GlassCard className="p-5 grid gap-2">
            <Row k="URL" v={url} mono />
            <Row k="Depth" v={depth} />
            <Row k="Modules" v={modules.length ? modules.join(", ") : "None"} />
            <Row k="Tasks" v={tasks.length ? tasks.join(" · ") : "None"} />
            <Row k="Device" v={device} />
          </GlassCard>

          <button
            type="button"
            onClick={onLaunch}
            disabled={isLoading}
            className="h-14 w-full rounded-xl font-semibold flex items-center justify-center gap-2"
            style={{
              background: "linear-gradient(135deg, #00D4FF, #7C3AED)",
              color: "#0A0C10",
              opacity: isLoading ? 0.7 : 1,
              boxShadow: "0 0 20px rgba(0,212,255,0.15), 0 0 40px rgba(0,212,255,0.05)",
            }}
          >
            {isLoading ? (
              <>
                <span className="h-4 w-4 rounded-full border-2 border-[rgba(10,12,16,0.35)] border-t-[rgba(10,12,16,0.9)] animate-spin" />
                Running QA…
              </>
            ) : (
              <>
                Launch QA Test <Rocket size={18} />
              </>
            )}
          </button>
          {isLoading ? (
            <div className="text-center text-sm" style={{ color: "var(--text-secondary)" }}>
              {progressMsg}
            </div>
          ) : null}

          <div className="flex justify-between gap-3">
            <button
              type="button"
              onClick={() => setCurrentStep(2)}
              className="h-11 px-4 rounded-xl font-semibold"
              style={{ background: "rgba(22,27,34,0.75)", color: "var(--text-secondary)", border: "1px solid rgba(48,54,61,0.7)" }}
            >
              ← Back
            </button>
          </div>
        </GlassCard>
      ) : null}
    </motion.div>
  );
}

function Row({ k, v, mono }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
        {k}
      </div>
      <div className={mono ? "font-mono text-sm text-right" : "text-sm text-right"} style={{ color: "var(--text-primary)" }}>
        {String(v)}
      </div>
    </div>
  );
}

function StepHeader({ current, onStep }) {
  const steps = [
    { n: 1, label: "Configure" },
    { n: 2, label: "Options" },
    { n: 3, label: "Launch" },
  ];
  return (
    <div className="flex justify-center">
      <div className="glass px-4 py-3 w-full max-w-[880px]">
        <div className="flex items-center justify-between gap-3">
          {steps.map((s, i) => (
            <div key={s.n} className="flex-1 flex items-center gap-3">
              <button
                type="button"
                onClick={() => onStep(s.n)}
                className="h-9 w-9 rounded-full grid place-items-center font-semibold"
                style={{
                  background:
                    s.n < current
                      ? "rgba(0,200,150,0.18)"
                      : s.n === current
                        ? "rgba(0,212,255,0.18)"
                        : "rgba(48,54,61,0.55)",
                  border: "1px solid rgba(48,54,61,0.7)",
                  color: s.n < current ? "var(--success)" : s.n === current ? "var(--accent-cyan)" : "var(--text-secondary)",
                }}
              >
                {s.n < current ? "✓" : s.n}
              </button>
              <div className="min-w-0">
                <div className="text-sm font-semibold" style={{ color: s.n === current ? "var(--accent-cyan)" : "var(--text-secondary)" }}>
                  {s.label}
                </div>
              </div>
              {i < steps.length - 1 ? (
                <div className="hidden md:block flex-1 h-px" style={{ background: "rgba(48,54,61,0.7)" }} />
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function DepthCard({ title, meta, desc, icon: Icon, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="glass p-4 text-left hover:scale-[1.01]"
      style={{
        border: active ? "1px solid rgba(0,212,255,0.6)" : "1px solid rgba(48,54,61,0.7)",
        background: active ? "rgba(0,212,255,0.06)" : "rgba(15,17,23,0.8)",
      }}
    >
      <div className="flex items-center justify-between">
        <div className="font-display font-bold">{title}</div>
        <div style={{ color: active ? "var(--accent-cyan)" : "var(--text-secondary)" }}>
          <Icon size={18} />
        </div>
      </div>
      <div className="mt-2 text-sm font-mono" style={{ color: "var(--text-secondary)" }}>
        {meta}
      </div>
      <div className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
        {desc}
      </div>
    </button>
  );
}

function DeviceButton({ label, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="h-12 rounded-xl font-semibold"
      style={{
        background: active ? "rgba(0,212,255,0.18)" : "rgba(22,27,34,0.75)",
        color: active ? "var(--accent-cyan)" : "var(--text-secondary)",
        border: active ? "1px solid rgba(0,212,255,0.45)" : "1px solid rgba(48,54,61,0.7)",
      }}
    >
      {label}
    </button>
  );
}

