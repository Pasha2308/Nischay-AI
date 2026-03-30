import { motion } from "framer-motion";
import { ExternalLink } from "lucide-react";
import { GlassCard } from "../components/ui/GlassCard";

const CARDS = [
  { group: "CI/CD PIPELINES", items: ["GitHub Actions", "GitLab CI", "Jenkins", "CircleCI"] },
  { group: "COMMUNICATION", items: ["Slack", "Microsoft Teams", "Discord", "Email"] },
  { group: "PROJECT MANAGEMENT", items: ["Jira", "Linear", "Trello", "Asana"] },
  { group: "MONITORING", items: ["Webhook", "Zapier", "PagerDuty", "Datadog"] },
];

export function Integrations() {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: "easeOut" }} className="grid gap-6 md:ml-[240px]">
      <div className="font-display text-2xl font-extrabold">Integrations</div>

      {CARDS.map((g) => (
        <div key={g.group} className="grid gap-3">
          <div className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
            {g.group}
          </div>
          <div className="grid gap-4 md:grid-cols-4">
            {g.items.map((name) => (
              <GlassCard key={name} className="p-5 hover:scale-[1.01]">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-display font-bold">{name}</div>
                    <div className="text-sm mt-2" style={{ color: "var(--text-secondary)" }}>
                      Available
                    </div>
                  </div>
                  <div className="h-10 w-10 rounded-xl grid place-items-center" style={{ background: "rgba(124,58,237,0.12)", border: "1px solid rgba(48,54,61,0.65)", color: "var(--accent-violet)" }}>
                    {name.slice(0, 1)}
                  </div>
                </div>
                <button
                  type="button"
                  className="mt-4 h-10 w-full rounded-xl font-semibold"
                  style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}
                >
                  Connect
                </button>
              </GlassCard>
            ))}
          </div>
        </div>
      ))}

      <GlassCard className="p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="font-display font-bold text-lg">REST API</div>
            <div className="text-sm mt-2" style={{ color: "var(--text-secondary)" }}>
              Base URL: <span className="font-mono" style={{ color: "var(--accent-cyan)" }}>http://localhost:8000</span>
            </div>
          </div>
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="h-11 px-4 rounded-xl font-semibold inline-flex items-center gap-2"
            style={{ background: "rgba(0,212,255,0.14)", color: "var(--accent-cyan)", border: "1px solid rgba(0,212,255,0.35)" }}
          >
            View API Docs <ExternalLink size={16} />
          </a>
        </div>
      </GlassCard>
    </motion.div>
  );
}

