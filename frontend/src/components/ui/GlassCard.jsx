export function GlassCard({ children, className = "" }) {
  return <div className={`glass shadow-glow ${className}`}>{children}</div>;
}

