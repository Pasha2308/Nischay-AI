import { useState, useEffect } from "react";
import { API, INTERVALS } from "../config/api";

export function useBackendHealth() {
  const [isOnline, setIsOnline] = useState(null);
  const [version, setVersion] = useState(null);

  const check = async () => {
    try {
      const controller = new AbortController();
      const t = setTimeout(() => controller.abort(), 3000);
      const res = await fetch(API.health, { signal: controller.signal });
      clearTimeout(t);
      if (res.ok) {
        const data = await res.json().catch(() => ({}));
        setIsOnline(true);
        setVersion(data.version ?? null);
      } else {
        setIsOnline(false);
      }
    } catch {
      setIsOnline(false);
    }
  };

  useEffect(() => {
    check();
    const interval = setInterval(check, INTERVALS.healthCheck);
    return () => clearInterval(interval);
  }, []);

  return { isOnline, version };
}
