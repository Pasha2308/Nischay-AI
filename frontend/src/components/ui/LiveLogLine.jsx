function colorFor(type) {
  const t = String(type || "").toUpperCase();
  if (t.includes("CRAWL")) return "var(--accent-cyan)";
  if (t.includes("PLAN")) return "var(--accent-violet)";
  if (t.includes("DETECT")) return "var(--warning)";
  if (t.includes("ERROR")) return "var(--danger)";
  if (t.includes("SCORE")) return "var(--success)";
  return "var(--text-primary)";
}

export function LiveLogLine({ type, message, timestamp }) {
  const c = colorFor(type);
  return (
    <div
      className="grid gap-2 items-start px-3 py-2 rounded-lg"
      style={{
        gridTemplateColumns: "84px 70px 1fr",
        background: "rgba(10,12,16,0.55)",
        border: "1px solid rgba(33,38,45,0.75)",
      }}
    >
      <div className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
        {timestamp}
      </div>
      <div className="text-xs font-mono font-semibold" style={{ color: c }}>
        [{type}]
      </div>
      <div className="text-sm font-mono" style={{ color: "var(--text-primary)" }}>
        {message}
      </div>
    </div>
  );
}

