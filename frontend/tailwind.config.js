/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["Syne", "system-ui", "sans-serif"],
        sans: ["DM Sans", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        base: "var(--bg-base)",
        surface: "var(--bg-surface)",
        elevated: "var(--bg-elevated)",
        borderSubtle: "var(--border-subtle)",
        borderActive: "var(--border-active)",
        accentCyan: "var(--accent-cyan)",
        accentViolet: "var(--accent-violet)",
        success: "var(--success)",
        warning: "var(--warning)",
        danger: "var(--danger)",
        high: "var(--high)",
        textPrimary: "var(--text-primary)",
        textSecondary: "var(--text-secondary)",
        textMuted: "var(--text-muted)",
      },
      boxShadow: {
        glow: "0 0 20px rgba(0,212,255,0.15), 0 0 40px rgba(0,212,255,0.05)",
      },
      borderRadius: {
        glass: "12px",
      },
    },
  },
  plugins: [],
};

