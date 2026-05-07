"use client";

import { CheckCheck } from "lucide-react";
import type { HandledToday, HandledTodayItem } from "../watch-mock";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";

interface HandledTodayPanelProps {
  handled: HandledToday;
  lang: Lang;
}

export function HandledTodayPanel({ handled, lang }: HandledTodayPanelProps) {
  const hasRows = handled.recent.length > 0;

  return (
    <div className="card bg-surface-2/55 border border-border-subtle rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <CheckCheck size={12} className="text-emerald-300" />
        <span className="maya-section-label">
          {watchStrings.rails.handledToday[lang]}
        </span>
      </div>

      <div className="text-[28px] leading-none font-semibold text-white tabular-nums mb-2">
        {handled.count}
      </div>

      {hasRows ? (
        <div className="flex flex-col divide-y divide-white/5">
          {handled.recent.map((item, i) => (
            <Row key={`${item.phone}-${i}`} item={item} />
          ))}
        </div>
      ) : (
        <div className="text-[11px] text-white/55">
          {watchStrings.handledToday.empty[lang]}
        </div>
      )}
    </div>
  );
}

function Row({ item }: { item: HandledTodayItem }) {
  return (
    <div className="py-2 flex items-baseline gap-2">
      <span className="text-[12.5px] text-white/85 truncate flex-1">
        {item.leadName}
      </span>
      <span className="text-[10px] text-white/55 truncate">
        {item.statusLabel}
      </span>
      <span className="text-[10px] text-white/40 shrink-0">{item.ago}</span>
    </div>
  );
}
