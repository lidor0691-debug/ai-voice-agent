"use client";

import { Users } from "lucide-react";
import type { LeadStage } from "../watch-mock";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";

interface LeadPipelineProps {
  stages: LeadStage[];
  lang: Lang;
}

export function LeadPipeline({ stages, lang }: LeadPipelineProps) {
  return (
    <div className="card bg-surface-2/55 border border-border-subtle rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Users size={12} className="text-brand-200" />
        <span className="maya-section-label">{watchStrings.rails.leadPipeline[lang]}</span>
      </div>
      <div className="flex flex-col gap-2.5">
        {stages.map(s => (
          <div key={s.stage}>
            <div className="flex items-baseline justify-between mb-1">
              <span className="text-[12px] text-white/80">{s.stage}</span>
              <span className="text-[12px] text-white/55 tabular-nums">{s.n}</span>
            </div>
            <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-brand-500 to-brand-200"
                style={{ width: `${Math.round(s.pct * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
