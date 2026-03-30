import { GlassCard } from "./GlassCard";

export function MetricCard({ title, value, subtitle, icon: Icon, color = "var(--accent-cyan)", right }) {
  return (
    <GlassCard className="metricPulse p-4 hover:scale-[1.02] hover:shadow-glow">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
            {title}
          </div>
          <div className="mt-2 text-3xl font-semibold font-mono" style={{ color: "var(--text-primary)" }}>
            {value}
          </div>
          <div className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
            {subtitle}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {right}
          <div
            className="h-10 w-10 rounded-xl grid place-items-center"
            style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.65)", color }}
          >
            {Icon ? <Icon size={18} /> : null}
          </div>
        </div>
      </div>
    </GlassCard>
  );
}

