import { useCallback, useMemo, useState } from "react";

export function useToast() {
  const [toasts, setToasts] = useState([]);

  const push = useCallback((t) => {
    const id = `t_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    const toast = { id, type: t.type ?? "info", title: t.title ?? "", message: t.message ?? "" };
    setToasts((prev) => [toast, ...prev].slice(0, 3));
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== id));
    }, 3000);
  }, []);

  const api = useMemo(
    () => ({
      toasts,
      push,
      success(message, title = "Success") {
        push({ type: "success", title, message });
      },
      error(message, title = "Couldn’t complete") {
        push({ type: "error", title, message });
      },
      info(message, title = "Info") {
        push({ type: "info", title, message });
      },
    }),
    [toasts, push],
  );

  return api;
}

