import { AlertTriangle, ShieldAlert, ShieldCheck, Shield } from "lucide-react";

function norm(level) {
  const s = String(level || "").toUpperCase();
  if (s.includes("CRITICAL")) return "CRITICAL";
  if (s.includes("HIGH")) return "HIGH";
  if (s.includes("MEDIUM")) return "MEDIUM";
  return "LOW";
}

export function SeverityBadge({ level = "LOW" }) {
  const l = norm(level);
  const cfg =
    l === "CRITICAL"
      ? { c: "var(--danger)", bg: "rgba(255,68,68,0.12)", Icon: ShieldAlert }
      : l === "HIGH"
        ? { c: "var(--high)", bg: "rgba(255,107,53,0.12)", Icon: AlertTriangle }
        : l === "MEDIUM"
          ? { c: "var(--warning)", bg: "rgba(245,166,35,0.12)", Icon: Shield }
          : { c: "var(--success)", bg: "rgba(0,200,150,0.12)", Icon: ShieldCheck };
  const Icon = cfg.Icon;
  return (
    <span
      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold"
      style={{ background: cfg.bg, color: cfg.c, border: `1px solid rgba(48,54,61,0.6)` }}
    >
      <Icon size={14} />
      {l}
    </span>
  );
}

