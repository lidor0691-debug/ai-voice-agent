"use client";

import { Check, X, ChevronRight } from "lucide-react";
import type { HeroRecommendation } from "../watch-mock";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";

interface HeroRecommendationProps {
  hero: HeroRecommendation;
  lang: Lang;
  onApprove?: () => void;
  onDecline?: () => void;
}

export function HeroRecommendationCard({ hero, lang, onApprove, onDecline }: HeroRecommendationProps) {
  const t = watchStrings.hero;
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
          onClick={onApprove}
          className="btn-primary flex items-center gap-2 px-4 h-9 rounded-lg bg-brand-500 hover:bg-brand-400 text-white text-[13px] font-medium"
        >
          <Check size={14} />
          {t.primary[lang]}
        </button>
        <button className="btn-ghost px-3 h-9 rounded-lg text-white/75 hover:bg-white/5 text-[13px]">
          {t.secondary[lang]}
        </button>
        <div className="ms-auto flex items-center gap-2 text-[12px] text-white/55">
          <ChevronRight size={12} />
          <span className="truncate max-w-[160px]">{hero.action}</span>
        </div>
        <button
          onClick={onDecline}
          aria-label={t.decline[lang]}
          className="btn-ghost w-9 h-9 grid place-items-center rounded-lg text-white/45 hover:bg-white/5"
        >
          <X size={14} />
        </button>
      </div>
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
