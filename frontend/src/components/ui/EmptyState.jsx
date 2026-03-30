import { GlassCard } from "./GlassCard";

export function EmptyState({ icon: Icon, title, subtitle, actionLabel, onAction }) {
  return (
    <GlassCard className="p-8 text-center grid gap-3 place-items-center">
      {Icon ? (
        <div
          className="h-12 w-12 rounded-2xl grid place-items-center"
          style={{ background: "rgba(0,212,255,0.12)", border: "1px solid rgba(48,54,61,0.65)", color: "var(--accent-cyan)" }}
        >
          <Icon size={22} />
        </div>
      ) : null}
      <div className="font-display text-xl font-bold" style={{ color: "var(--text-primary)" }}>
        {title}
      </div>
      <div className="text-sm max-w-[520px]" style={{ color: "var(--text-secondary)" }}>
        {subtitle}
      </div>
      {actionLabel ? (
        <button
          type="button"
          onClick={onAction}
          className="mt-2 px-4 h-11 rounded-xl font-semibold"
          style={{
            background: "linear-gradient(135deg, rgba(0,212,255,1), rgba(124,58,237,1))",
            color: "#0A0C10",
            boxShadow: "0 0 20px rgba(0,212,255,0.15), 0 0 40px rgba(0,212,255,0.05)",
          }}
        >
          {actionLabel}
        </button>
      ) : null}
    </GlassCard>
  );
}

