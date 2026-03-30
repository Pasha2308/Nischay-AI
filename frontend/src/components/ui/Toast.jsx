import { CheckCircle2, Info, XCircle } from "lucide-react";

function iconFor(type) {
  if (type === "success") return CheckCircle2;
  if (type === "error") return XCircle;
  return Info;
}

function colorFor(type) {
  if (type === "success") return "var(--success)";
  if (type === "error") return "var(--danger)";
  return "var(--accent-cyan)";
}

export function ToastHost({ toasts = [] }) {
  return (
    <div className="fixed right-4 top-4 z-50 grid gap-2">
      {toasts.map((t) => {
        const Icon = iconFor(t.type);
        const c = colorFor(t.type);
        return (
          <div
            key={t.id}
            className="glass px-4 py-3 w-[320px]"
            style={{ border: "1px solid rgba(48,54,61,0.7)" }}
          >
            <div className="flex items-start gap-3">
              <div className="mt-0.5" style={{ color: c }}>
                <Icon size={18} />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                  {t.title}
                </div>
                <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
                  {t.message}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

