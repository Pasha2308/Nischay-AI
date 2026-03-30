export function ToggleSwitch({ checked, onChange, label }) {
  return (
    <label className="flex items-center justify-between gap-4">
      <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
        {label}
      </span>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className="relative h-7 w-12 rounded-full"
        style={{
          background: checked ? "rgba(0,212,255,0.22)" : "rgba(48,54,61,0.55)",
          border: "1px solid rgba(48,54,61,0.7)",
        }}
        aria-pressed={checked}
      >
        <span
          className="absolute top-1 h-5 w-5 rounded-full"
          style={{
            left: checked ? 26 : 4,
            background: checked ? "var(--accent-cyan)" : "rgba(139,148,158,0.85)",
            boxShadow: checked ? "0 0 16px rgba(0,212,255,0.22)" : "none",
          }}
        />
      </button>
    </label>
  );
}

