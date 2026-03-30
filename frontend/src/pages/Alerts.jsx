import { motion } from "framer-motion";
import { Bell, Hash, Link as LinkIcon, Mail } from "lucide-react";
import { GlassCard } from "../components/ui/GlassCard";

export function Alerts() {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: "easeOut" }} className="grid gap-6 md:ml-[240px]">
      <div className="font-display text-2xl font-extrabold">Alerts</div>

      <div className="grid gap-4 md:grid-cols-2">
        <Channel icon={Mail} title="Email" status="Available" action="Configure" />
        <Channel icon={Hash} title="Slack" status="Available" action="Connect to Slack" />
        <Channel icon={LinkIcon} title="Webhook" status="Available" action="Configure" />
        <Channel icon={Bell} title="In-app" status="Enabled" action="Manage" />
      </div>

      <GlassCard className="p-5">
        <div className="font-display font-bold text-lg">Alert Rules</div>
        <div className="mt-3 grid gap-2 text-sm" style={{ color: "var(--text-secondary)" }}>
          <div className="glass px-3 py-2 flex items-center justify-between">
            <span>Critical Alert</span>
            <span className="font-mono">risk_score &gt; 80</span>
          </div>
          <div className="glass px-3 py-2 flex items-center justify-between">
            <span>Failure Alert</span>
            <span className="font-mono">run failed</span>
          </div>
        </div>
      </GlassCard>
    </motion.div>
  );
}

function Channel({ icon: Icon, title, status, action }) {
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
        <button type="button" className="h-10 px-3 rounded-xl font-semibold" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}>
          {action}
        </button>
      </div>
    </GlassCard>
  );
}

