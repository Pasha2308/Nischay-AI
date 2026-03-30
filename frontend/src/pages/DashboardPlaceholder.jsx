import { motion } from "framer-motion";
import { GlassCard } from "../components/ui/GlassCard";

export function DashboardPlaceholder({ title, subtitle }) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, ease: "easeOut" }} className="grid gap-6 md:ml-[240px]">
      <div className="font-display text-2xl font-extrabold">{title}</div>
      <GlassCard className="p-6">
        <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
          {subtitle}
        </div>
      </GlassCard>
    </motion.div>
  );
}

