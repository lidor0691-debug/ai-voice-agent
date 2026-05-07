"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
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
            <Row key={`${item.phone}-${i}`} item={item} lang={lang} />
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

function Row({ item, lang }: { item: HandledTodayItem; lang: Lang }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const t = watchStrings.handledToday;

  // Stage 8C-2 — derive decision_id client-side from (status, phone). The
  // backend's parse_decision_id accepts this exact format; we don't need a
  // new field on the recent row.
  const decisionId =
    item.status && item.phone ? `decision:${item.status}:${item.phone}` : null;
  const canUndo = Boolean(decisionId) && !pending;

  async function handleUndo() {
    if (!decisionId || pending) return;
    setPending(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/home/watch/decisions/${encodeURIComponent(decisionId)}/undo`,
        { method: "POST", cache: "no-store" },
      );
      if (!res.ok) {
        setError(t.undoError[lang]);
        setPending(false);
        return;
      }
      // Success — refresh the server-rendered page so /briefing re-runs and
      // this row drops out of handled_today (decision returns to hero if
      // status still matches). The component unmounts on next render, so
      // we don't need to reset pending — leaves the button visually settled
      // until React swaps the panel content.
      router.refresh();
    } catch {
      setError(t.undoError[lang]);
      setPending(false);
    }
  }

  return (
    <div className="py-2">
      <div className="flex items-baseline gap-2">
        <span className="text-[12.5px] text-white/85 truncate flex-1">
          {item.leadName}
        </span>
        <span className="text-[10px] text-white/55 truncate">
          {item.statusLabel}
        </span>
        <span className="text-[10px] text-white/40 shrink-0">{item.ago}</span>
        <button
          type="button"
          onClick={handleUndo}
          disabled={!canUndo}
          className="text-[10px] text-white/45 hover:text-amber-300/85 disabled:text-white/20 disabled:cursor-not-allowed transition-colors shrink-0 ms-1"
        >
          {pending ? t.undoPending[lang] : t.undo[lang]}
        </button>
      </div>
      {error && (
        <div
          role="alert"
          className="text-[10px] text-amber-300/85 mt-1 flex items-center gap-1.5"
        >
          <span className="w-1 h-1 rounded-full bg-amber-400 shrink-0" />
          <span className="truncate">{error}</span>
        </div>
      )}
    </div>
  );
}
