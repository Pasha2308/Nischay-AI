import { motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { Bug, CheckCircle2, MoreVertical, X } from "lucide-react";
import { DndContext, PointerSensor, useDroppable, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GlassCard } from "../components/ui/GlassCard";
import { SeverityBadge } from "../components/ui/SeverityBadge";
import { EmptyState } from "../components/ui/EmptyState";
import { BASE_URL } from "../config/api";

function colFor(status) {
  const s = String(status || "").toLowerCase();
  if (s === "resolved") return "RESOLVED";
  if (s === "ignored") return "IGNORED";
  return "OPEN";
}

function apiUrl(path) {
  return `${BASE_URL}${path}`;
}

function severityToBorder(sev) {
  const s = String(sev || "").toLowerCase();
  if (s === "critical") return "#ef4444";
  if (s === "high") return "#f97316";
  if (s === "medium") return "#eab308";
  if (s === "low") return "#3b82f6";
  return "rgba(48,54,61,0.9)";
}

function fmtDateShort(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return "—";
  }
}

function shortPath(u) {
  if (!u) return "";
  try {
    const url = new URL(u);
    return url.pathname || "/";
  } catch {
    return String(u).slice(0, 80);
  }
}

export function IssuesTracker() {
  const [q, setQ] = useState("");
  const [sev, setSev] = useState("all");
  const [stats, setStats] = useState(null);
  const [items, setItems] = useState({ OPEN: [], RESOLVED: [], IGNORED: [] });
  const [loading, setLoading] = useState({ OPEN: false, RESOLVED: false, IGNORED: false });
  const [err, setErr] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [selected, setSelected] = useState(null);
  const [toast, setToast] = useState("");
  const toastTimer = useRef(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  function showToast(msg) {
    setToast(msg);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(""), 1800);
  }

  async function fetchStats() {
    try {
      const r = await fetch(apiUrl("/issues/stats"));
      if (!r.ok) throw new Error(await r.text());
      setStats(await r.json());
    } catch (e) {
      setErr(`Failed to load issue stats: ${String(e?.message || e)}`);
    }
  }

  async function fetchColumn(col) {
    const status = col === "OPEN" ? "open" : col === "RESOLVED" ? "resolved" : "ignored";
    const params = new URLSearchParams({
      status,
      severity: sev || "all",
      limit: "100",
      offset: "0",
    });
    setLoading((x) => ({ ...x, [col]: true }));
    setErr("");
    try {
      const r = await fetch(apiUrl(`/issues?${params.toString()}`));
      if (!r.ok) throw new Error(await r.text());
      const j = await r.json();
      setItems((x) => ({ ...x, [col]: Array.isArray(j.items) ? j.items : [] }));
    } catch (e) {
      setErr(`Failed to load ${status} issues: ${String(e?.message || e)}`);
    } finally {
      setLoading((x) => ({ ...x, [col]: false }));
    }
  }

  async function refreshAll() {
    await Promise.all([fetchStats(), fetchColumn("OPEN"), fetchColumn("RESOLVED"), fetchColumn("IGNORED")]);
  }

  useEffect(() => {
    refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sev]);

  useEffect(() => {
    async function loadSelected() {
      if (!selectedId) {
        setSelected(null);
        return;
      }
      try {
        const r = await fetch(apiUrl(`/issues/${selectedId}`));
        if (!r.ok) throw new Error(await r.text());
        setSelected(await r.json());
      } catch (e) {
        showToast(`Failed to load issue: ${String(e?.message || e)}`);
      }
    }
    loadSelected();
  }, [selectedId]);

  const filtered = useMemo(() => {
    const term = String(q || "").trim().toLowerCase();
    if (!term) return items;
    const match = (i) =>
      String(i.title || "").toLowerCase().includes(term) ||
      String(i.page_url || "").toLowerCase().includes(term);
    return {
      OPEN: (items.OPEN || []).filter(match),
      RESOLVED: (items.RESOLVED || []).filter(match),
      IGNORED: (items.IGNORED || []).filter(match),
    };
  }, [items, q]);

  async function patchStatus(id, status) {
    const r = await fetch(apiUrl(`/issues/${id}`), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (!r.ok) throw new Error(await r.text());
    return await r.json();
  }

  async function moveIssue(activeId, fromCol, toCol) {
    const toStatus = toCol === "OPEN" ? "open" : toCol === "RESOLVED" ? "resolved" : "ignored";
    const src = Array.from(items[fromCol] || []);
    const dst = Array.from(items[toCol] || []);
    const idx = src.findIndex((x) => String(x.id) === String(activeId));
    if (idx < 0) return;
    const [moved] = src.splice(idx, 1);
    const optimistic = { ...moved, status: toStatus };
    dst.unshift(optimistic);
    setItems((x) => ({ ...x, [fromCol]: src, [toCol]: dst }));
    try {
      const updated = await patchStatus(activeId, toStatus);
      setItems((x) => ({
        ...x,
        [toCol]: (x[toCol] || []).map((it) => (String(it.id) === String(activeId) ? updated : it)),
      }));
      await fetchStats();
      showToast("Issue updated");
    } catch (e) {
      // rollback via refresh
      showToast(`Update failed: ${String(e?.message || e)}`);
      await refreshAll();
    }
  }

  function findColById(id) {
    for (const col of ["OPEN", "RESOLVED", "IGNORED"]) {
      if ((items[col] || []).some((x) => String(x.id) === String(id))) return col;
    }
    return null;
  }

  async function onDragEnd(evt) {
    const activeId = evt?.active?.id;
    const overId = evt?.over?.id;
    if (!activeId || !overId) return;
    const fromCol = findColById(activeId);
    const toCol = String(overId);
    if (!fromCol || !["OPEN", "RESOLVED", "IGNORED"].includes(toCol)) return;
    if (fromCol === toCol) return;
    await moveIssue(activeId, fromCol, toCol);
  }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: "easeOut" }} className="grid gap-6 md:ml-[240px]">
      <div className="flex items-center justify-between gap-3">
        <div className="font-display text-2xl font-extrabold">Issues Tracker</div>
        <div className="flex items-center gap-2">
          <select
            value={sev}
            onChange={(e) => setSev(e.target.value)}
            className="h-11 rounded-xl px-3 outline-none"
            style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-primary)" }}
          >
            <option value="all">All severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search issues…"
            className="h-11 rounded-xl px-3 outline-none w-[260px]"
            style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }}
          />
        </div>
      </div>

      {err ? (
        <GlassCard className="p-4">
          <div className="text-sm" style={{ color: "var(--danger)" }}>
            {err}
          </div>
        </GlassCard>
      ) : null}

      <DndContext sensors={sensors} onDragEnd={onDragEnd}>
        <div className="grid gap-4 md:grid-cols-3">
          <Column
            id="OPEN"
            title="OPEN"
            color="var(--danger)"
            count={stats?.open ?? (items.OPEN || []).length}
            itemCount={(filtered.OPEN || []).length}
            emptyState={
              <div className="grid place-items-center py-10 text-center">
                <CheckCircle2 className="h-9 w-9" style={{ color: "var(--success)" }} />
                <div className="mt-2 font-semibold">No open issues — great job!</div>
                <div className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
                  New defects will show up here as scans run.
                </div>
              </div>
            }
          >
            <SortableContext items={(filtered.OPEN || []).map((x) => String(x.id))} strategy={verticalListSortingStrategy}>
              {(filtered.OPEN || []).map((i) => (
                <IssueCard key={i.id} issue={i} onOpen={() => setSelectedId(i.id)} onAction={async (st) => {
                  try {
                    await patchStatus(i.id, st);
                    await refreshAll();
                    showToast("Issue updated");
                  } catch (e) {
                    showToast(`Update failed: ${String(e?.message || e)}`);
                  }
                }} />
              ))}
            </SortableContext>
            {loading.OPEN ? <div className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>Loading…</div> : null}
          </Column>

          <Column
            id="RESOLVED"
            title="RESOLVED"
            color="var(--success)"
            count={stats?.resolved ?? (items.RESOLVED || []).length}
            itemCount={(filtered.RESOLVED || []).length}
            emptyState={
              <div className="grid place-items-center py-10 text-center">
                <div className="font-semibold">No resolved issues yet</div>
                <div className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
                  Mark issues resolved to track progress over time.
                </div>
              </div>
            }
          >
            <SortableContext items={(filtered.RESOLVED || []).map((x) => String(x.id))} strategy={verticalListSortingStrategy}>
              {(filtered.RESOLVED || []).map((i) => (
                <IssueCard key={i.id} issue={i} onOpen={() => setSelectedId(i.id)} onAction={async (st) => {
                  try {
                    await patchStatus(i.id, st);
                    await refreshAll();
                    showToast("Issue updated");
                  } catch (e) {
                    showToast(`Update failed: ${String(e?.message || e)}`);
                  }
                }} />
              ))}
            </SortableContext>
            {loading.RESOLVED ? <div className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>Loading…</div> : null}
          </Column>

          <Column
            id="IGNORED"
            title="IGNORED"
            color="var(--text-muted)"
            count={stats?.ignored ?? (items.IGNORED || []).length}
            itemCount={(filtered.IGNORED || []).length}
            emptyState={
              <div className="grid place-items-center py-10 text-center">
                <div className="font-semibold">No ignored issues</div>
                <div className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
                  Ignore noisy issues you don’t want to track.
                </div>
              </div>
            }
          >
            <SortableContext items={(filtered.IGNORED || []).map((x) => String(x.id))} strategy={verticalListSortingStrategy}>
              {(filtered.IGNORED || []).map((i) => (
                <IssueCard key={i.id} issue={i} onOpen={() => setSelectedId(i.id)} onAction={async (st) => {
                  try {
                    await patchStatus(i.id, st);
                    await refreshAll();
                    showToast("Issue updated");
                  } catch (e) {
                    showToast(`Update failed: ${String(e?.message || e)}`);
                  }
                }} />
              ))}
            </SortableContext>
            {loading.IGNORED ? <div className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>Loading…</div> : null}
          </Column>
        </div>
      </DndContext>

      {!((filtered.OPEN || []).length + (filtered.RESOLVED || []).length + (filtered.IGNORED || []).length) ? (
        <EmptyState
          icon={Bug}
          title="No issues matched"
          subtitle="Adjust filters to view issues across runs."
          actionLabel="Reset filters"
          onAction={() => {
            setQ("");
            setSev("all");
          }}
        />
      ) : null}

      <IssueDetailPanel
        issue={selected}
        onClose={() => setSelectedId(null)}
        onAction={async (st) => {
          if (!selected?.id) return;
          try {
            await patchStatus(selected.id, st);
            await refreshAll();
            setSelectedId(null);
            showToast("Issue updated");
          } catch (e) {
            showToast(`Update failed: ${String(e?.message || e)}`);
          }
        }}
      />

      {toast ? (
        <div className="fixed bottom-6 right-6 z-[60] px-4 py-3 rounded-xl text-sm" style={{ background: "rgba(22,27,34,0.92)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-primary)" }}>
          {toast}
        </div>
      ) : null}
    </motion.div>
  );
}

function Column({ id, title, color, count, emptyState, itemCount, children }) {
  return (
    <GlassCard className="p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
          <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
            {title}
          </div>
        </div>
        <div className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
          {count}
        </div>
      </div>
      <DroppableArea id={id}>
        <div className="mt-3 grid gap-3">{children}</div>
      </DroppableArea>
      {itemCount === 0 ? emptyState : null}
    </GlassCard>
  );
}

function DroppableArea({ id, children }) {
  const { setNodeRef, isOver } = useDroppable({ id });
  return (
    <div ref={setNodeRef} style={isOver ? { outline: "1px dashed rgba(148,163,184,0.55)", outlineOffset: 6, borderRadius: 12 } : null}>
      {children}
    </div>
  );
}

function IssueCard({ issue, onOpen, onAction }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: String(issue.id) });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
  };
  const [menuOpen, setMenuOpen] = useState(false);
  const border = severityToBorder(issue.severity);

  return (
    <div
      ref={setNodeRef}
      style={{ ...style, borderLeft: `4px solid ${border}` }}
      className="glass p-4 hover:translate-y-[-1px] cursor-pointer"
      onClick={onOpen}
      {...attributes}
      {...listeners}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <SeverityBadge level={issue.severity} />
            <span className="text-xs font-mono px-2 py-0.5 rounded-full" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-muted)" }}>
              {String(issue.business_impact || "ux")}
            </span>
          </div>
          <div className="mt-2 text-sm font-semibold truncate">{issue.title || "Untitled issue"}</div>
          <div className="text-xs font-mono truncate mt-1" style={{ color: "var(--text-secondary)" }}>
            {shortPath(issue.page_url)}
          </div>
        </div>
        <div className="relative">
          <button
            className="h-9 w-9 grid place-items-center rounded-lg"
            style={{ background: "rgba(22,27,34,0.45)", border: "1px solid rgba(48,54,61,0.55)" }}
            onClick={(e) => {
              e.stopPropagation();
              setMenuOpen((x) => !x);
            }}
            aria-label="Issue actions"
          >
            <MoreVertical className="h-4 w-4" />
          </button>
          {menuOpen ? (
            <div
              className="absolute right-0 mt-2 w-44 rounded-xl overflow-hidden"
              style={{ background: "rgba(16,20,26,0.98)", border: "1px solid rgba(48,54,61,0.7)" }}
              onClick={(e) => e.stopPropagation()}
            >
              <button className="w-full text-left px-3 py-2 text-sm hover:bg-white/5" onClick={() => { setMenuOpen(false); onAction?.("resolved"); }}>
                Mark as Resolved
              </button>
              <button className="w-full text-left px-3 py-2 text-sm hover:bg-white/5" onClick={() => { setMenuOpen(false); onAction?.("ignored"); }}>
                Ignore
              </button>
              <button className="w-full text-left px-3 py-2 text-sm hover:bg-white/5" onClick={() => { setMenuOpen(false); onOpen?.(); }}>
                View Details
              </button>
            </div>
          ) : null}
        </div>
      </div>

      <div className="mt-3 text-sm" style={{ color: "var(--text-secondary)", maxHeight: 62, overflow: "hidden" }}>
        {issue.user_view || issue.description || "—"}
      </div>
      <div className="mt-3 flex items-center justify-between text-xs" style={{ color: "var(--text-muted)" }}>
        <span>First seen {fmtDateShort(issue.first_seen_at)}</span>
        <span className="px-2 py-1 rounded-full" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)" }}>
          Seen in {issue.scan_count ?? 1} runs
        </span>
      </div>
    </div>
  );
}

function IssueDetailPanel({ issue, onClose, onAction }) {
  const open = Boolean(issue?.id);
  if (!open) return null;
  const scans = Array.isArray(issue.scan_ids) ? issue.scan_ids : [];
  const screenshot = issue.screenshot_path ? String(issue.screenshot_path) : "";

  return (
    <div className="fixed inset-0 z-[55]">
      <div className="absolute inset-0" style={{ background: "rgba(0,0,0,0.35)" }} onClick={onClose} />
      <div
        className="absolute right-0 top-0 h-full w-[400px] p-4 overflow-y-auto"
        style={{ background: "rgba(13,17,23,0.98)", borderLeft: "1px solid rgba(48,54,61,0.7)" }}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <SeverityBadge level={issue.severity} />
              <div className="text-xs font-mono px-2 py-0.5 rounded-full" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-muted)" }}>
                {String(issue.business_impact || "ux")}
              </div>
            </div>
            <div className="mt-2 font-semibold break-words">{issue.title || "Untitled issue"}</div>
          </div>
          <button
            className="h-9 w-9 grid place-items-center rounded-lg"
            style={{ background: "rgba(22,27,34,0.45)", border: "1px solid rgba(48,54,61,0.55)" }}
            onClick={onClose}
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-4">
          <div className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>Page URL</div>
          <a className="mt-1 block text-sm break-words underline" href={issue.page_url} target="_blank" rel="noreferrer">
            {issue.page_url}
          </a>
        </div>

        <Section title="Description">
          <div className="text-sm whitespace-pre-wrap" style={{ color: "var(--text-secondary)" }}>
            {issue.description || "—"}
          </div>
        </Section>

        <Section title="Element affected">
          <code className="block text-xs whitespace-pre-wrap p-3 rounded-xl" style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-primary)" }}>
            {issue.element || "—"}
          </code>
        </Section>

        <Section title="User impact">
          <div className="text-sm whitespace-pre-wrap" style={{ color: "var(--text-secondary)" }}>
            {issue.user_view || "—"}
          </div>
        </Section>

        <Section title="How to fix">
          <div className="text-sm whitespace-pre-wrap p-3 rounded-xl" style={{ background: "rgba(20,83,45,0.18)", border: "1px solid rgba(34,197,94,0.25)", color: "var(--text-primary)" }}>
            {issue.how_to_fix || "—"}
          </div>
        </Section>

        <Section title={`Seen in ${issue.scan_count ?? scans.length ?? 1} scans`}>
          {scans.length ? (
            <div className="text-xs font-mono grid gap-1" style={{ color: "var(--text-muted)" }}>
              {scans.slice(0, 25).map((sid) => (
                <div key={sid}>Scan #{sid}</div>
              ))}
            </div>
          ) : (
            <div className="text-sm" style={{ color: "var(--text-muted)" }}>—</div>
          )}
        </Section>

        {screenshot ? (
          <Section title="Screenshot">
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              Screenshot available: <code>{screenshot}</code>
            </div>
          </Section>
        ) : null}

        <div className="mt-6 flex items-center gap-2">
          <button
            className="h-11 px-4 rounded-xl text-sm font-semibold"
            style={{ background: "rgba(34,197,94,0.18)", border: "1px solid rgba(34,197,94,0.25)", color: "var(--text-primary)" }}
            onClick={() => onAction?.("resolved")}
          >
            Mark Resolved
          </button>
          <button
            className="h-11 px-4 rounded-xl text-sm font-semibold"
            style={{ background: "rgba(148,163,184,0.10)", border: "1px solid rgba(148,163,184,0.22)", color: "var(--text-primary)" }}
            onClick={() => onAction?.("ignored")}
          >
            Ignore
          </button>
          <button
            className="h-11 px-4 rounded-xl text-sm font-semibold ml-auto"
            style={{ background: "rgba(22,27,34,0.75)", border: "1px solid rgba(48,54,61,0.7)", color: "var(--text-primary)" }}
            onClick={() => {
              try {
                navigator.clipboard?.writeText(window.location.href);
              } catch {
                // ignore
              }
            }}
          >
            Copy Link
          </button>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="mt-5">
      <div className="text-xs font-semibold" style={{ color: "var(--text-muted)" }}>
        {title}
      </div>
      <div className="mt-2">{children}</div>
    </div>
  );
}

