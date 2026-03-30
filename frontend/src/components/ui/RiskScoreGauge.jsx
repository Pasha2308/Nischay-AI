import { useEffect, useMemo, useState } from "react";

function colorForScore(score) {
  if (score >= 81) return "var(--danger)";
  if (score >= 61) return "var(--high)";
  if (score >= 31) return "var(--warning)";
  return "var(--success)";
}

function levelForScore(score) {
  if (score >= 81) return "CRITICAL";
  if (score >= 61) return "HIGH";
  if (score >= 31) return "MEDIUM";
  return "LOW";
}

export function RiskScoreGauge({ score = 0 }) {
  const s = Math.max(0, Math.min(100, Number(score) || 0));
  const c = useMemo(() => colorForScore(s), [s]);
  const lvl = useMemo(() => levelForScore(s), [s]);

  const r = 80;
  const cx = 100;
  const cy = 100;
  const startAngle = 180;
  const endAngle = 0;

  const [anim, setAnim] = useState(0);
  const [num, setNum] = useState(0);

  useEffect(() => {
    setAnim(0);
    setNum(0);
    const t0 = performance.now();
    const dur = 1200;
    let raf = 0;
    function tick(now) {
      const p = Math.min(1, (now - t0) / dur);
      const ease = 1 - Math.pow(1 - p, 3);
      setAnim(ease);
      setNum(Math.round(s * ease));
      if (p < 1) raf = requestAnimationFrame(tick);
    }
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [s]);

  function polarToCartesian(angleDeg) {
    const a = ((angleDeg - 90) * Math.PI) / 180.0;
    return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  }

  function arcPath(a0, a1) {
    const p0 = polarToCartesian(a1);
    const p1 = polarToCartesian(a0);
    const largeArc = a1 - a0 <= 180 ? 0 : 1;
    return `M ${p0.x} ${p0.y} A ${r} ${r} 0 ${largeArc} 0 ${p1.x} ${p1.y}`;
  }

  const track = arcPath(startAngle, endAngle);
  const fillAngle = startAngle + (endAngle - startAngle) * (anim * (s / 100));
  const fill = arcPath(startAngle, fillAngle);

  return (
    <div className="glass p-5 flex items-center gap-5">
      <svg width="200" height="120" viewBox="0 0 200 120">
        <path d={track} stroke="rgba(48,54,61,0.9)" strokeWidth="14" fill="none" strokeLinecap="round" />
        <path
          d={fill}
          stroke={c}
          strokeWidth="14"
          fill="none"
          strokeLinecap="round"
          style={{ filter: "drop-shadow(0 0 12px rgba(0,212,255,0.14))" }}
        />
      </svg>
      <div className="min-w-0">
        <div className="text-[11px] tracking-[0.18em] uppercase" style={{ color: "var(--text-muted)" }}>
          Risk level
        </div>
        <div className="mt-1 font-mono text-5xl leading-none" style={{ color: c }}>
          {num}
        </div>
        <div className="mt-2 font-display text-lg font-bold" style={{ color: c }}>
          {lvl} RISK
        </div>
      </div>
    </div>
  );
}

