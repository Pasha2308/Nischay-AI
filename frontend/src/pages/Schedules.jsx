import { motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { CalendarClock, MoreVertical, Plus, Play } from "lucide-react";
import { GlassCard } from "../components/ui/GlassCard";
import { EmptyState } from "../components/ui/EmptyState";
import { ToggleSwitch } from "../components/ui/ToggleSwitch";

export function Schedules() {
  const [toastMsg, setToastMsg] = useState("");
  const [open, setOpen] = useState(false); // new schedule modal
  const [edit, setEdit] = useState(null); // schedule object
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  const baseUrl = useMemo(() => {
    if (typeof window !== "undefined" && window.location && window.location.hostname) {
      const h = window.location.hostname;
      if (h === "localhost" || h === "127.0.0.1") return "http://localhost:8000";
    }
    return "https://api.nischay.ai";
  }, []);

  async function refresh() {
    setLoading(true);
    try {
      const res = await fetch(`${baseUrl}/schedules`);
      const data = await res.json();
      setRows(Array.isArray(data) ? data : []);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseUrl]);

  useEffect(() => {
    if (!toastMsg) return;
    const t = window.setTimeout(() => setToastMsg(""), 2600);
    return () => window.clearTimeout(t);
  }, [toastMsg]);

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: "easeOut" }} className="grid gap-6 md:ml-[240px]">
      <div className="flex items-center justify-between gap-3">
        <div className="font-display text-2xl font-extrabold">Schedules</div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="h-11 px-4 rounded-xl font-semibold inline-flex items-center gap-2"
          style={{ background: "rgba(0,212,255,0.14)", color: "var(--accent-cyan)", border: "1px solid rgba(0,212,255,0.35)" }}
        >
          <Plus size={16} /> New Schedule
        </button>
      </div>

      {loading ? (
        <GlassCard className="p-5">
          <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
            Loading schedules…
          </div>
        </GlassCard>
      ) : !rows.length ? (
        <EmptyState
          icon={CalendarClock}
          title="No schedules configured"
          subtitle="Automate your QA testing on a fixed cadence"
          actionLabel="+ Create your first schedule"
          onAction={() => setOpen(true)}
        />
      ) : (
        <div className="grid gap-4">
          {rows.map((s) => (
            <ScheduleCard
              key={s.id}
              schedule={s}
              baseUrl={baseUrl}
              onRunFailed={(msg) => setToastMsg(msg)}
              onEdit={() => setEdit(s)}
              onDeleted={refresh}
              onUpdated={refresh}
            />
          ))}
        </div>
      )}

      {toastMsg ? (
        <div className="fixed bottom-4 right-4 z-50 glass px-4 py-3" style={{ border: "1px solid rgba(48,54,61,0.75)" }}>
          <div className="text-sm font-semibold" style={{ color: "var(--warning)" }}>
            {toastMsg}
          </div>
        </div>
      ) : null}

      {open ? (
        <ScheduleModal
          mode="create"
          baseUrl={baseUrl}
          onClose={() => setOpen(false)}
          onSaved={() => {
            setOpen(false);
            refresh();
          }}
        />
      ) : null}

      {edit ? (
        <ScheduleModal
          mode="edit"
          baseUrl={baseUrl}
          initial={edit}
          onClose={() => setEdit(null)}
          onSaved={() => {
            setEdit(null);
            refresh();
          }}
        />
      ) : null}
    </motion.div>
  );
}

const FLOW_OPTIONS = ["auth", "browse", "cart", "checkout", "support", "ui"];
const FLOW_LABEL = {
  auth: "Auth",
  browse: "Browse",
  cart: "Cart",
  checkout: "Checkout",
  support: "Support",
  ui: "UI",
};

const TZ_OPTIONS = [
  "UTC",
  "America/New_York",
  "America/Los_Angeles",
  "Europe/London",
  "Asia/Kolkata",
  "Asia/Tokyo",
  "Australia/Sydney",
];

function _pad2(n) {
  const v = String(n);
  return v.length === 1 ? `0${v}` : v;
}

function buildDailyCron(timeHHMM) {
  const [hh, mm] = String(timeHHMM || "09:00").split(":");
  return `${Number(mm) || 0} ${Number(hh) || 9} * * *`;
}

function buildWeeklyCron(dayIdx, timeHHMM) {
  // Cron day-of-week: 0=Sun, 1=Mon ... 6=Sat
  const [hh, mm] = String(timeHHMM || "09:00").split(":");
  return `${Number(mm) || 0} ${Number(hh) || 9} * * ${Number(dayIdx)}`;
}

function formatNextRun(dtIso) {
  if (!dtIso) return "—";
  try {
    const d = new Date(dtIso);
    return d.toLocaleString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return String(dtIso);
  }
}

function formatLastRunLine(s) {
  if (!s?.last_run_at) return null;
  try {
    const d = new Date(s.last_run_at);
    const risk = typeof s?.last_risk_score === "number" ? s.last_risk_score : null;
    const issues = typeof s?.last_issues === "number" ? s.last_issues : null;
    const parts = [`Last run: ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`];
    if (risk != null) parts.push(`Risk score ${risk}`);
    if (issues != null) parts.push(`${issues} issues`);
    return parts.join(" — ");
  } catch {
    return `Last run: ${s.last_run_at}`;
  }
}

function FlowBadges({ flows = [] }) {
  const list = Array.isArray(flows) ? flows : [];
  if (!list.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {list.map((f) => (
        <span
          key={f}
          className="px-2 py-1 rounded-full text-xs font-semibold"
          style={{ background: "rgba(0,212,255,0.12)", border: "1px solid rgba(48,54,61,0.65)", color: "var(--accent-cyan)" }}
        >
          {FLOW_LABEL[f] || String(f)}
        </span>
      ))}
    </div>
  );
}

function ScheduleCard({ schedule, baseUrl, onRunFailed, onEdit, onDeleted, onUpdated }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [toggleBusy, setToggleBusy] = useState(false);
  const url = String(schedule.url || "");
  const nextRun = formatNextRun(schedule.next_run_at);
  const lastLine = formatLastRunLine(schedule);

  return (
    <GlassCard className="p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-[160px]">
          <ToggleSwitch
            checked={Boolean(schedule.is_active)}
            onChange={async (val) => {
              if (toggleBusy) return;
              setToggleBusy(true);
              try {
                await fetch(`${baseUrl}/schedules/${schedule.id}`, {
                  method: "PUT",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ ...schedule, is_active: Boolean(val), flows: schedule.flows || [] }),
                });
              } finally {
                setToggleBusy(false);
                onUpdated();
              }
            }}
            label={Boolean(schedule.is_active) ? "Active" : "Inactive"}
          />
        </div>

        <div className="flex-1 grid gap-2">
          <div className="font-display font-bold text-lg">{schedule.name || "Schedule"}</div>
          <div className="text-sm truncate" style={{ color: "var(--text-secondary)" }} title={url}>
            {url}
          </div>
          <FlowBadges flows={schedule.flows || []} />
          <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
            Next run: <span className="font-mono">{nextRun}</span>
          </div>
          {lastLine ? (
            <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
              {lastLine}
            </div>
          ) : null}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={async () => {
              if (running) return;
              setRunning(true);
              try {
                const res = await fetch(`${baseUrl}/schedules/${schedule.id}/run`, { method: "POST" });
                if (!res.ok) {
                  const data = await res.json().catch(() => ({}));
                  onRunFailed?.(data?.detail ? `Run now failed: ${data.detail}` : "Run now failed");
                }
              } catch (e) {
                onRunFailed?.(`Run now failed: ${String(e?.message || e)}`);
              } finally {
                setRunning(false);
                onUpdated();
              }
            }}
            className="h-10 px-3 rounded-xl font-semibold inline-flex items-center gap-2"
            style={{ background: "rgba(0,212,255,0.14)", color: "var(--accent-cyan)", border: "1px solid rgba(0,212,255,0.35)" }}
          >
            <Play size={16} />
            {running ? "Running…" : "Run Now"}
          </button>

          <div className="relative">
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              className="h-10 w-10 rounded-xl grid place-items-center"
              style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}
              aria-label="Schedule menu"
            >
              <MoreVertical size={16} />
            </button>
            {menuOpen ? (
              <div
                className="absolute right-0 mt-2 w-[180px] glass p-2"
                style={{ border: "1px solid rgba(48,54,61,0.75)" }}
              >
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    onEdit?.();
                  }}
                  className="h-9 w-full rounded-lg text-left px-3 text-sm"
                  style={{ color: "var(--text-secondary)" }}
                >
                  Edit
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    setMenuOpen(false);
                    await fetch(`${baseUrl}/schedules/${schedule.id}`, { method: "DELETE" });
                    onDeleted?.();
                  }}
                  className="h-9 w-full rounded-lg text-left px-3 text-sm"
                  style={{ color: "var(--warning)" }}
                >
                  Delete
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </GlassCard>
  );
}

function ScheduleModal({ mode, baseUrl, onClose, onSaved, initial }) {
  const [name, setName] = useState(initial?.name || "");
  const [url, setUrl] = useState(initial?.url || "");
  const [flows, setFlows] = useState(() => {
    const f = initial?.flows;
    if (Array.isArray(f) && f.length) return f;
    return [...FLOW_OPTIONS]; // all checked by default
  });
  const [freq, setFreq] = useState("daily"); // daily|weekly|custom
  const [timeHHMM, setTimeHHMM] = useState("09:00");
  const [tz, setTz] = useState(initial?.timezone || "UTC");
  const [weekDay, setWeekDay] = useState(1); // Mon
  const [cron, setCron] = useState(initial?.cron_expression || buildDailyCron("09:00"));
  const [isActive, setIsActive] = useState(initial?.is_active ?? true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (mode === "edit" && initial?.cron_expression) {
      setCron(String(initial.cron_expression));
      setFreq("custom");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggleFlow(f) {
    setFlows((prev) => {
      const set = new Set(prev);
      if (set.has(f)) set.delete(f);
      else set.add(f);
      return Array.from(set);
    });
  }

  async function submit() {
    setError("");
    const nm = name.trim();
    const u = url.trim();
    if (!nm) return setError("Schedule name is required.");
    if (!u || !u.startsWith("http")) return setError("Target URL must start with http(s)://");

    let cronExpr = cron.trim();
    if (freq === "daily") cronExpr = buildDailyCron(timeHHMM);
    if (freq === "weekly") cronExpr = buildWeeklyCron(weekDay, timeHHMM);
    if (freq === "custom") cronExpr = cron.trim();

    setSaving(true);
    try {
      const payload = {
        name: nm,
        url: u,
        flows: flows.length ? flows : [],
        cron_expression: cronExpr,
        timezone: tz,
        is_active: Boolean(isActive),
      };
      const endpoint = mode === "edit" ? `${baseUrl}/schedules/${initial.id}` : `${baseUrl}/schedules`;
      const method = mode === "edit" ? "PUT" : "POST";
      const res = await fetch(endpoint, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data?.detail || "Could not save schedule.");
        return;
      }
      onSaved?.(data);
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0" style={{ background: "rgba(10,12,16,0.65)", backdropFilter: "blur(6px)" }} onClick={onClose} />
      <div className="absolute left-1/2 top-1/2 w-[min(760px,92vw)] -translate-x-1/2 -translate-y-1/2 glass p-5">
        <div className="font-display text-xl font-bold">{mode === "edit" ? "Edit Schedule" : "New Schedule"}</div>

        <div className="mt-4 grid gap-4">
          <div className="grid gap-2">
            <label className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
              Schedule name
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Daily checkout audit"
              className="h-11 rounded-xl px-3 outline-none"
              style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }}
            />
          </div>

          <div className="grid gap-2">
            <label className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
              Target URL
            </label>
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://your-app.com"
              className="h-11 rounded-xl px-3 outline-none"
              style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }}
            />
          </div>

          <div className="grid gap-2">
            <label className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
              Select flows
            </label>
            <div className="grid gap-2 md:grid-cols-3">
              {FLOW_OPTIONS.map((f) => (
                <label key={f} className="glass px-3 py-2 rounded-xl flex items-center gap-2">
                  <input type="checkbox" checked={flows.includes(f)} onChange={() => toggleFlow(f)} />
                  <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
                    {FLOW_LABEL[f]}
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div className="grid gap-2">
            <label className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
              Frequency
            </label>
            <div className="grid gap-2">
              <label className="glass px-3 py-2 rounded-xl flex items-center gap-2">
                <input type="radio" checked={freq === "daily"} onChange={() => setFreq("daily")} />
                <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
                  Daily
                </span>
              </label>
              {freq === "daily" ? (
                <div className="grid gap-2 md:grid-cols-2">
                  <input
                    type="time"
                    value={timeHHMM}
                    onChange={(e) => setTimeHHMM(e.target.value)}
                    className="h-11 rounded-xl px-3 outline-none"
                    style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-primary)" }}
                  />
                  <select
                    value={tz}
                    onChange={(e) => setTz(e.target.value)}
                    className="h-11 rounded-xl px-3 outline-none"
                    style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-primary)" }}
                  >
                    {TZ_OPTIONS.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>
              ) : null}

              <label className="glass px-3 py-2 rounded-xl flex items-center gap-2">
                <input type="radio" checked={freq === "weekly"} onChange={() => setFreq("weekly")} />
                <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
                  Weekly
                </span>
              </label>
              {freq === "weekly" ? (
                <div className="grid gap-2">
                  <div className="flex flex-wrap gap-2">
                    {[
                      ["Mon", 1],
                      ["Tue", 2],
                      ["Wed", 3],
                      ["Thu", 4],
                      ["Fri", 5],
                      ["Sat", 6],
                      ["Sun", 0],
                    ].map(([lbl, idx]) => (
                      <button
                        key={lbl}
                        type="button"
                        onClick={() => setWeekDay(idx)}
                        className="h-9 px-3 rounded-xl text-sm font-semibold"
                        style={{
                          background: weekDay === idx ? "rgba(0,212,255,0.14)" : "rgba(22,27,34,0.75)",
                          color: weekDay === idx ? "var(--accent-cyan)" : "var(--text-secondary)",
                          border: "1px solid rgba(48,54,61,0.7)",
                        }}
                      >
                        {lbl}
                      </button>
                    ))}
                  </div>
                  <div className="grid gap-2 md:grid-cols-2">
                    <input
                      type="time"
                      value={timeHHMM}
                      onChange={(e) => setTimeHHMM(e.target.value)}
                      className="h-11 rounded-xl px-3 outline-none"
                      style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-primary)" }}
                    />
                    <select
                      value={tz}
                      onChange={(e) => setTz(e.target.value)}
                      className="h-11 rounded-xl px-3 outline-none"
                      style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-primary)" }}
                    >
                      {TZ_OPTIONS.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              ) : null}

              <label className="glass px-3 py-2 rounded-xl flex items-center gap-2">
                <input type="radio" checked={freq === "custom"} onChange={() => setFreq("custom")} />
                <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
                  Custom
                </span>
              </label>
              {freq === "custom" ? (
                <div className="grid gap-2">
                  <input
                    value={cron}
                    onChange={(e) => setCron(e.target.value)}
                    placeholder="0 9 * * 1"
                    className="h-11 rounded-xl px-3 outline-none font-mono"
                    style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }}
                  />
                  <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
                    e.g. <span className="font-mono">0 9 * * 1</span> = every Monday at 9am{" "}
                    <a href="https://crontab.guru/" target="_blank" rel="noreferrer" style={{ color: "var(--accent-cyan)" }}>
                      Cron expression guide ↗
                    </a>
                  </div>
                  <select
                    value={tz}
                    onChange={(e) => setTz(e.target.value)}
                    className="h-11 rounded-xl px-3 outline-none"
                    style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-primary)" }}
                  >
                    {TZ_OPTIONS.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>
              ) : null}
            </div>
          </div>

          <div className="glass px-3 py-2 rounded-xl">
            <ToggleSwitch checked={Boolean(isActive)} onChange={setIsActive} label="Active" />
          </div>

          {error ? (
            <div className="text-sm" style={{ color: "var(--warning)" }}>
              {error}
            </div>
          ) : null}

          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={onClose}
              className="h-11 px-4 rounded-xl font-semibold"
              style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={saving}
              onClick={submit}
              className="h-11 px-4 rounded-xl font-semibold"
              style={{ background: "linear-gradient(135deg, #00D4FF, #7C3AED)", color: "#0A0C10", opacity: saving ? 0.7 : 1 }}
            >
              {saving ? "Saving…" : mode === "edit" ? "Save Changes" : "Create Schedule"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

