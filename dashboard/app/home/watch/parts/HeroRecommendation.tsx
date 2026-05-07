"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, X, ChevronRight } from "lucide-react";
import type { HeroRecommendation, WhatsAppThread } from "../watch-mock";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";
import { HeroDetailsModal } from "./HeroDetailsModal";

interface HeroRecommendationProps {
  hero: HeroRecommendation;
  lang: Lang;
  /** Stage 9A — full WhatsApp thread list, used by HeroDetailsModal to find
   *  the conversation matching this hero's phone. Optional so the card still
   *  renders in contexts where threads aren't passed. */
  whatsapp?: WhatsAppThread[];
  /** Legacy parent log handler — fires after a successful action so the
   *  WatchShell console.log still surfaces. The act flow itself does NOT
   *  depend on this prop. */
  onApprove?: () => void;
  onDecline?: () => void;
}

export function HeroRecommendationCard({ hero, lang, whatsapp, onApprove, onDecline }: HeroRecommendationProps) {
  const t = watchStrings.hero;
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);

  // Stage 9A — pre-filter the matching thread by phone so the modal stays
  // a thin presenter. Returns undefined when no live phone or no matching
  // thread (modal renders the empty conversation state).
  const matchingThread = useMemo<WhatsAppThread | undefined>(() => {
    if (!hero.phone || !whatsapp || whatsapp.length === 0) return undefined;
    return whatsapp.find(t => t.phone === hero.phone);
  }, [hero.phone, whatsapp]);

  // Stage 9A — disable details when there's no actionable hero. Quiet/failed
  // states have no rich context to show.
  const canShowDetails = Boolean(hero.id);

  // Reset local state when the underlying decision changes — e.g. after
  // router.refresh() lands a fresh hero following a successful action.
  // useState survives rerenders on the same component instance, so without
  // this effect the `pending` flag would stay true forever and the button
  // would be stuck on "מעדכן..." even after the new hero rendered.
  // Stage 9A — also auto-closes the details modal when the hero swaps so
  // the operator never reads stale context for a different decision.
  useEffect(() => {
    setPending(false);
    setError(null);
    setDetailsOpen(false);
  }, [hero.id]);

  // Stage 7 — the action surface only fires when the live mapping carried
  // a backend decision id. Quiet-live, fetch-failed, and demo states leave
  // hero.id undefined; the button stays visible (preserves layout) but
  // disabled.
  const canAct = Boolean(hero.id) && !pending;

  async function handleApprove() {
    if (!hero.id || pending) return;
    setPending(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/home/watch/decisions/${encodeURIComponent(hero.id)}/act`,
        { method: "POST", cache: "no-store" },
      );
      if (!res.ok) {
        setError(t.actError[lang]);
        setPending(false);
        return;
      }
      // Success — refresh the server-rendered page so /briefing re-runs
      // and this acted decision drops out of the open list. The hero
      // either advances to the next decision or shows the quiet-live
      // monitoring state. No optimistic removal — server is source of truth.
      onApprove?.();
      router.refresh();
      // `pending` is reset by the [hero.id] effect above once router.refresh
      // brings in the new decision. If refresh somehow fails to change the
      // hero (e.g. backend didn't suppress), the button stays disabled until
      // the user navigates or hard-refreshes — acceptable degraded mode
      // since the action insert itself is durable.
    } catch {
      setError(t.actError[lang]);
      setPending(false);
    }
  }

  return (
    <>
    <div className="
      relative card maya-fade-in
      bg-gradient-to-br from-surface-2/82 to-surface-1/62
      backdrop-blur-xl
      border border-border-strong rounded-2xl
      p-4 pe-5
      shadow-[0_24px_60px_-24px_rgba(0,0,0,0.65)]
      overflow-hidden
    ">
      <div className="maya-tone-bar" />

      <div className="flex items-baseline justify-between mb-1.5">
        <div className="maya-section-label">{t.title[lang]}</div>
        <div className="text-[11px] text-white/45">{hero.window}</div>
      </div>

      <h2 className="text-[19px] leading-tight text-white font-semibold tracking-tight mb-0.5">
        {hero.headline}
      </h2>
      <div className="text-[12px] text-white/55 mb-2">
        {hero.target} · <span className="text-brand-200">{hero.value}</span>
      </div>

      {hero.delivery && (
        <div className={`text-[11px] mb-2 flex items-center gap-1.5 ${
          hero.delivery.tone === "warn" ? "text-amber-300" : "text-emerald-300/90"
        }`}>
          <span className={`w-1.5 h-1.5 rounded-full ${
            hero.delivery.tone === "warn" ? "bg-amber-400" : "bg-emerald-400"
          }`} />
          <span className="truncate">{hero.delivery.label}</span>
        </div>
      )}

      <div className="mb-2">
        <div className="maya-section-label mb-1">{t.why[lang]}</div>
        <ul className="space-y-0.5">
          {hero.why.map((reason, i) => (
            <li key={i} className="flex items-start gap-2 text-[12.5px] text-white/80 leading-snug">
              <span className="mt-1.5 w-1 h-1 rounded-full bg-brand-200 shrink-0" />
              <span>{reason}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex items-center gap-4 mb-2.5 text-[12px]">
        <ConfidenceMeter pct={hero.confidence} label={t.confidence[lang]} />
        <div className="h-6 w-px bg-white/10" />
        <div>
          <div className="text-white/45 text-[10px] uppercase tracking-wider">{t.expectedLift[lang]}</div>
          <div className="text-emerald-300 font-medium">{hero.impact}</div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handleApprove}
          disabled={!canAct}
          className="btn-primary flex items-center gap-2 px-4 h-9 rounded-lg bg-brand-500 hover:bg-brand-400 disabled:bg-brand-500/40 disabled:cursor-not-allowed text-white text-[13px] font-medium"
        >
          <Check size={14} />
          {pending ? t.primaryPending[lang] : t.primary[lang]}
        </button>
        <button
          type="button"
          onClick={() => setDetailsOpen(true)}
          disabled={!canShowDetails}
          className="btn-ghost px-3 h-9 rounded-lg text-white/75 hover:bg-white/5 disabled:text-white/30 disabled:cursor-not-allowed text-[13px]"
        >
          {t.secondary[lang]}
        </button>
        <div className="ms-auto flex items-center gap-2 text-[12px] text-white/55">
          <ChevronRight size={12} />
          <span className="truncate max-w-[160px]">{hero.action}</span>
        </div>
        <button
          type="button"
          onClick={onDecline}
          aria-label={t.decline[lang]}
          className="btn-ghost w-9 h-9 grid place-items-center rounded-lg text-white/45 hover:bg-white/5"
        >
          <X size={14} />
        </button>
      </div>

      {error && (
        <div
          role="alert"
          className="mt-2 text-[11px] text-amber-300/90 flex items-center gap-1.5"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
          <span className="truncate">{error}</span>
        </div>
      )}
    </div>

    {detailsOpen && canShowDetails && (
      <HeroDetailsModal
        hero={hero}
        thread={matchingThread}
        lang={lang}
        onClose={() => setDetailsOpen(false)}
      />
    )}
    </>
  );
}

function ConfidenceMeter({ pct, label }: { pct: number; label: string }) {
  const r = 14;
  const c = 2 * Math.PI * r;
  const offset = c - (pct / 100) * c;
  return (
    <div className="flex items-center gap-2">
      <svg width="36" height="36" viewBox="0 0 36 36" className="-rotate-90">
        <circle cx="18" cy="18" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="2" />
        <circle
          cx="18" cy="18" r={r}
          fill="none"
          stroke="rgb(110,220,200)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
        />
      </svg>
      <div>
        <div className="text-white/45 text-[10px] uppercase tracking-wider">{label}</div>
        <div className="text-white font-medium">{pct}%</div>
      </div>
    </div>
  );
}
