"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, X, ChevronRight } from "lucide-react";
import type { HeroRecommendation } from "../watch-mock";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";

interface HeroRecommendationProps {
  hero: HeroRecommendation;
  lang: Lang;
  /** Legacy parent log handler — fires after a successful action so the
   *  WatchShell console.log still surfaces. The act flow itself does NOT
   *  depend on this prop. */
  onApprove?: () => void;
  onDecline?: () => void;
}

export function HeroRecommendationCard({ hero, lang, onApprove, onDecline }: HeroRecommendationProps) {
  const t = watchStrings.hero;
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      // Leave `pending` true through refresh so the button stays disabled
      // until React re-renders with the new hero. If refresh fails, the
      // user sees the spinner — better than re-enabling on a stale card.
    } catch {
      setError(t.actError[lang]);
      setPending(false);
    }
  }

  return (
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
        <button type="button" className="btn-ghost px-3 h-9 rounded-lg text-white/75 hover:bg-white/5 text-[13px]">
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
