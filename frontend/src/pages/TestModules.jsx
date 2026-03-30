import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { GlassCard } from "../components/ui/GlassCard";
import { ToggleSwitch } from "../components/ui/ToggleSwitch";
import { API } from "../config/api";

const FALLBACK_MODULES = [
  { id: "auth", name: "Authentication", description: "Test login, signup, password reset", enabled: true, test_count: 12, status: "available" },
  { id: "navigation", name: "Navigation", description: "Menu, links, breadcrumbs, 404s", enabled: true, test_count: 10, status: "available" },
  { id: "search", name: "Search", description: "Keywords, filters, sorting, pagination", enabled: true, test_count: 8, status: "available" },
  { id: "product", name: "Product Listing", description: "Grid, badges, images, quick view", enabled: true, test_count: 9, status: "available" },
  { id: "product_detail", name: "Product Detail", description: "Images, variants, add to cart", enabled: true, test_count: 11, status: "available" },
  { id: "cart", name: "Shopping Cart", description: "Add, remove, quantities, totals", enabled: true, test_count: 10, status: "available" },
  { id: "checkout", name: "Checkout", description: "Address, payment, order placement", enabled: true, test_count: 12, status: "available" },
  { id: "wishlist", name: "Wishlist", description: "Add, remove, move to cart", enabled: true, test_count: 6, status: "available" },
  { id: "performance", name: "Performance", description: "Load time, LCP, TTFB, assets", enabled: true, test_count: 7, status: "available" },
  { id: "accessibility", name: "Accessibility", description: "Alt text, labels, contrast, ARIA", enabled: true, test_count: 8, status: "available" },
  { id: "security", name: "Security", description: "XSS, injection, HTTPS, validation", enabled: true, test_count: 6, status: "available" },
  { id: "links_assets", name: "Links & Assets", description: "404s, broken images, missing resources", enabled: true, test_count: 8, status: "available" },
];

function normalizeModule(m) {
  return {
    id: m.id ?? String(m.name ?? "").toLowerCase().replace(/\s+/g, "_"),
    name: m.name ?? m.id ?? "Module",
    description: m.description ?? m.desc ?? "",
    enabled: m.enabled !== false,
    test_count: Number(m.test_count ?? m.tests ?? 12) || 0,
    status: m.status ?? "available",
  };
}

export function TestModules() {
  const [modules, setModules] = useState(FALLBACK_MODULES);
  const [enabled, setEnabled] = useState(() => Object.fromEntries(FALLBACK_MODULES.map((m) => [m.id, true])));
  const [tasks, setTasks] = useState(["Smoke checkout on staging", "Validate login and add-to-cart"]);
  const [taskInput, setTaskInput] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(API.getModules);
        if (!res.ok) throw new Error("bad status");
        const data = await res.json();
        const raw = Array.isArray(data?.modules) ? data.modules : [];
        const list = raw.length ? raw.map(normalizeModule) : FALLBACK_MODULES;
        if (cancelled) return;
        setModules(list);
        setEnabled((prev) => {
          const next = { ...prev };
          for (const m of list) {
            if (next[m.id] === undefined) next[m.id] = m.enabled !== false;
          }
          return next;
        });
      } catch {
        if (!cancelled) {
          setModules(FALLBACK_MODULES);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function addTask() {
    const t = taskInput.trim();
    if (!t) return;
    setTasks((p) => [t, ...p]);
    setTaskInput("");
  }

  function removeTask(t) {
    setTasks((p) => p.filter((x) => x !== t));
  }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: "easeOut" }} className="grid gap-6 md:ml-[240px]">
      <div className="font-display text-2xl font-extrabold">Test Modules</div>

      <div className="grid gap-4 md:grid-cols-3">
        {modules.map((m) => (
          <GlassCard key={m.id} className="p-5 hover:scale-[1.01]" style={{ opacity: enabled[m.id] ? 1 : 0.55 }}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="font-display font-bold text-lg">{m.name}</div>
                <div className="text-sm mt-2" style={{ color: "var(--text-secondary)" }}>
                  {m.description}
                </div>
              </div>
              <ToggleSwitch checked={!!enabled[m.id]} onChange={(v) => setEnabled((p) => ({ ...p, [m.id]: v }))} label="" />
            </div>
            <div className="mt-4 flex items-center justify-between text-xs" style={{ color: "var(--text-muted)" }}>
              <span className="px-2 py-1 rounded-full" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }}>
                {m.test_count} tests
              </span>
              <span className="px-2 py-1 rounded-full" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }}>
                {m.status === "available" ? "available" : m.status}
              </span>
            </div>
          </GlassCard>
        ))}
      </div>

      <GlassCard className="p-5">
        <div className="font-display font-bold text-lg">Custom Tasks</div>
        <div className="mt-3 grid gap-3 md:grid-cols-[1fr_auto]">
          <textarea
            value={taskInput}
            onChange={(e) => setTaskInput(e.target.value)}
            rows={2}
            className="w-full rounded-xl p-3 outline-none"
            style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }}
            placeholder="Add a custom QA task…"
          />
          <button
            type="button"
            onClick={addTask}
            className="h-11 px-4 rounded-xl font-semibold"
            style={{ background: "rgba(0,212,255,0.14)", color: "var(--accent-cyan)", border: "1px solid rgba(0,212,255,0.35)" }}
          >
            Add Task
          </button>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {tasks.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => removeTask(t)}
              className="px-3 py-2 rounded-full text-sm"
              style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-secondary)" }}
              title="Remove"
            >
              {t} ×
            </button>
          ))}
        </div>
      </GlassCard>
    </motion.div>
  );
}
