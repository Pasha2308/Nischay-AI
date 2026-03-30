export function LoadingSkeleton({ className = "", width, height }) {
  return (
    <div
      className={`rounded-xl ${className}`}
      style={{
        width: width ?? "100%",
        height: height ?? 16,
        border: "1px solid rgba(48,54,61,0.55)",
        background:
          "linear-gradient(90deg, rgba(22,27,34,0.65) 0%, rgba(48,54,61,0.35) 50%, rgba(22,27,34,0.65) 100%)",
        backgroundSize: "200% 100%",
        animation: "shimmer 1.2s ease-in-out infinite",
      }}
    />
  );
}

