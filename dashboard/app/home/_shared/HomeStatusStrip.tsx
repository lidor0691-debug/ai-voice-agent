"use client";

import { ArrowUp, ArrowDown, Minus } from "lucide-react";
import type { Kpi } from "../watch/watch-mock";

interface HomeStatusStripProps {
  kpis: Kpi[];
}

export function HomeStatusStrip({ kpis }: HomeStatusStripProps) {
  return (
    <div
      className="
        sticky top-0 z-10
        h-11 px-5
        flex items-center gap-5
        bg-surface-1/85 backdrop-blur-xl
        border-b border-border-subtle
      "
    >
      <div className="maya-section-label">LIVE</div>
      <div className="flex items-center gap-5 overflow-x-auto">
        {kpis.map(k => (
          <KpiChip key={k.key} kpi={k} />
        ))}
      </div>
    </div>
  );
}

function KpiChip({ kpi }: { kpi: Kpi }) {
  const Icon = kpi.dir === "up" ? ArrowUp : kpi.dir === "down" ? ArrowDown : Minus;
  const tone = kpi.dir === "up" ? "text-emerald-300" : kpi.dir === "down" ? "text-amber-300" : "text-white/50";
  return (
    <div className="flex items-baseline gap-2 whitespace-nowrap">
      <span className="text-[11px] text-white/55">{kpi.label}</span>
      <span className="text-[14px] font-medium text-white">{kpi.value}</span>
      <span className={`text-[11px] flex items-center gap-0.5 ${tone}`}>
        <Icon size={11} />
        {kpi.delta}
      </span>
    </div>
  );
}
