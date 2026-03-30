function colorFor(status) {
  const s = String(status || "").toLowerCase();
  if (s.includes("run") || s.includes("pending")) return "var(--accent-cyan)";
  if (s.includes("fail")) return "var(--danger)";
  if (s.includes("complete") || s.includes("success")) return "var(--success)";
  return "var(--text-muted)";
}

export function StatusDot({ status = "pending", label = true }) {
  const c = colorFor(status);
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className="h-2.5 w-2.5 rounded-full"
        style={{ background: c, animation: "pulseDot 2s ease-in-out infinite" }}
      />
      {label ? <span className="text-xs" style={{ color: "var(--text-secondary)" }}>{String(status)}</span> : null}
    </span>
  );
}

