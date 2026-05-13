"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { HandledToday, HandledTodayItem } from "../watch-mock";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";

interface HandledTodayPanelProps {
  handled: HandledToday;
  lang: Lang;
}

export function HandledTodayPanel({ handled, lang }: HandledTodayPanelProps) {
  const hasRows = handled.recent.length > 0;
  const today = new Date().toLocaleDateString(lang === "he" ? "he-IL" : "en-US", {
    weekday: "short", day: "numeric", month: "long",
  });

  return (
    <>
      <div className="maya-card__head">
        <div className="maya-card__title">{watchStrings.rails.handledToday[lang]}</div>
        <span className="maya-card__action">{today}</span>
      </div>

      {hasRows ? (
        <>
          <div className="maya-stat">
            <span className="maya-stat__v tnum">{handled.count}</span>
            <span className="maya-stat__l">
              {lang === "he" ? "פניות שמאיה טיפלה היום" : `${handled.count === 1 ? "lead" : "leads"} Maya handled today`}
            </span>
          </div>
          <div className="maya-list">
            {handled.recent.map((item, i) => (
              <Row key={`${item.phone}-${i}`} item={item} lang={lang} />
            ))}
          </div>
        </>
      ) : (
        <div className="maya-stat__l" style={{ fontStyle: "italic", marginTop: 6 }}>
          {lang === "he" ? "הכל טופל היום. מאיה ערה ומנטרת." : "All handled today. Maya is on watch."}
        </div>
      )}
    </>
  );
}

function Row({ item, lang }: { item: HandledTodayItem; lang: Lang }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const t = watchStrings.handledToday;

  const decisionId =
    item.status && item.phone ? `decision:${item.status}:${item.phone}` : null;
  const canUndo = Boolean(decisionId) && !pending;
  const tag =
    item.status?.includes("replied") ? "ok"
    : item.status?.includes("failed") ? "risk"
    : "wait";

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
      router.refresh();
    } catch {
      setError(t.undoError[lang]);
      setPending(false);
    }
  }

  return (
    <div className="maya-list__row maya-list__row--schedule">
      <span className="maya-list__time">{item.ago}</span>
      <div>
        <div className="maya-list__name">{item.leadName}</div>
        <div className="maya-list__sub">{item.statusLabel}</div>
        {error && (
          <div role="alert" style={{ fontSize: 10, color: "var(--down)", marginTop: 4 }}>
            {error}
          </div>
        )}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className={`maya-tag maya-tag--${tag}`}>{item.statusLabel}</span>
        <button
          type="button"
          onClick={handleUndo}
          disabled={!canUndo}
          style={{
            background: "transparent", border: 0,
            font: "inherit", fontSize: 10,
            color: "var(--ink-3)", cursor: canUndo ? "pointer" : "not-allowed",
            padding: "2px 4px",
          }}
        >
          {pending ? t.undoPending[lang] : t.undo[lang]}
        </button>
      </div>
    </div>
  );
}
