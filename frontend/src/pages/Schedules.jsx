import { motion } from "framer-motion";
import { useState } from "react";
import { CalendarClock, Plus } from "lucide-react";
import { GlassCard } from "../components/ui/GlassCard";
import { EmptyState } from "../components/ui/EmptyState";

export function Schedules() {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState([]);

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

      {!rows.length ? (
        <EmptyState
          icon={CalendarClock}
          title="No schedules configured"
          subtitle="Automate QA testing at a fixed cadence. This UI will connect automatically when the schedules endpoint is available."
          actionLabel="Create Schedule"
          onAction={() => setOpen(true)}
        />
      ) : (
        <GlassCard className="p-5">Schedules table</GlassCard>
      )}

      {open ? <SlideOver onClose={() => setOpen(false)} onCreate={(r) => { setRows((p) => [r, ...p]); setOpen(false); }} /> : null}
    </motion.div>
  );
}

function SlideOver({ onClose, onCreate }) {
  const [url, setUrl] = useState("https://example.com");
  const [cron, setCron] = useState("0 9 * * *");
  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0" style={{ background: "rgba(10,12,16,0.65)", backdropFilter: "blur(6px)" }} onClick={onClose} />
      <div className="absolute right-0 top-0 h-full w-full max-w-[420px] glass p-5">
        <div className="font-display text-xl font-bold">New Schedule</div>
        <div className="mt-4 grid gap-3">
          <label className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
            URL
          </label>
          <input value={url} onChange={(e) => setUrl(e.target.value)} className="h-11 rounded-xl px-3 outline-none" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }} />
          <label className="text-xs tracking-[0.18em] uppercase mt-2" style={{ color: "var(--text-muted)" }}>
            Cron
          </label>
          <input value={cron} onChange={(e) => setCron(e.target.value)} className="h-11 rounded-xl px-3 outline-none" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }} />
          <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
            Example: <span className="font-mono">0 9 * * *</span> runs daily at 09:00.
          </div>
          <button
            type="button"
            onClick={() => onCreate({ url, cron, active: true })}
            className="h-11 rounded-xl font-semibold"
            style={{ background: "linear-gradient(135deg, #00D4FF, #7C3AED)", color: "#0A0C10" }}
          >
            Create Schedule
          </button>
          <button
            type="button"
            onClick={onClose}
            className="h-11 rounded-xl font-semibold"
            style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

