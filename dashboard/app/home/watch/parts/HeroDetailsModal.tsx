"use client";

import { useEffect } from "react";
import { X } from "lucide-react";
import type { HeroRecommendation, WhatsAppThread, WhatsAppMessage } from "../watch-mock";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";

/** Map decision_status enum → Hebrew label. Mirrors the backend builder
 *  copy so the operator sees the same wording surfaced elsewhere
 *  (briefing decisions, WhatsApp panel). */
function statusLabelHe(status?: string): string {
  switch (status) {
    case "replied_after_followup": return "חזר אחרי שחזור";
    case "at_risk":                return "בסיכון";
    case "followup_pending":       return "ממתין למעקב";
    case "booked":                 return "תואם";
    case "no_response":            return "לא ענה";
    case "awaiting_attention":     return "ממתין לתשומת לב";
    default:                       return status ?? "—";
  }
}

interface HeroDetailsModalProps {
  hero: HeroRecommendation;
  /** Optional pre-filtered WhatsApp thread for this hero's phone. When
   *  absent, the conversation footer renders the empty state. */
  thread?: WhatsAppThread;
  lang: Lang;
  onClose: () => void;
}

export function HeroDetailsModal({ hero, thread, lang, onClose }: HeroDetailsModalProps) {
  const t = watchStrings.heroDetails;

  // Esc closes the modal — matches the WhatsAppPanel modal's pattern.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const statusLabel = statusLabelHe(hero.status);
  const conversation = thread?.messages ?? [];
  const hasConversation = conversation.length > 0;

  return (
    <div
      className="fixed inset-0 z-[100] grid place-items-center bg-black/60 backdrop-blur-sm maya-fade-in"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-full max-w-md mx-4 max-h-[85vh] overflow-y-auto bg-surface-2/95 backdrop-blur-xl border border-border-strong rounded-2xl shadow-[0_30px_80px_-20px_rgba(0,0,0,0.7)]"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/5">
          <div className="min-w-0">
            <div className="text-[14px] text-white/90 truncate">{hero.target}</div>
            <div className="text-[11px] text-white/50 mt-0.5 flex items-center gap-2">
              {hero.phone && (
                <span dir="ltr" className="tabular-nums [unicode-bidi:isolate]">
                  {hero.phone}
                </span>
              )}
              {hero.phone && hero.status && <span className="text-white/30">·</span>}
              {hero.status && <span>{statusLabel}</span>}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t.closeAria[lang]}
            className="w-8 h-8 grid place-items-center rounded-lg text-white/55 hover:bg-white/5 hover:text-white/85 focus:outline-none focus:ring-1 focus:ring-brand-400/40 shrink-0"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          {/* Situation */}
          <div className="text-[14px] text-white/90 leading-snug">
            {hero.headline}
          </div>

          {/* Why it matters */}
          {hero.why.length > 0 && (
            <Section title={t.whyItMatters[lang]}>
              <ul className="space-y-1">
                {hero.why.map((reason, i) => (
                  <li key={i} className="flex items-start gap-2 text-[12.5px] text-white/80 leading-snug">
                    <span className="mt-1.5 w-1 h-1 rounded-full bg-brand-200 shrink-0" />
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {/* Recommendation */}
          {hero.action && hero.action !== "—" && (
            <Section title={t.recommendation[lang]}>
              <div className="text-[12.5px] text-white/85 leading-snug">{hero.action}</div>
            </Section>
          )}

          {/* Suggested message — only when present */}
          {hero.suggestedMessage && (
            <Section title={t.suggestedMessage[lang]}>
              <div className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 text-[12.5px] text-white/90 leading-snug whitespace-pre-wrap break-words">
                {hero.suggestedMessage}
              </div>
            </Section>
          )}

          {/* Stats inline */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] pt-1 border-t border-white/5">
            <Stat label={t.confidenceLabel[lang]} value={`${hero.confidence}%`} />
            <Stat label={t.impactLabel[lang]} value={hero.impact} valueClass="text-emerald-300" />
            <Stat value={hero.window} />
          </div>
        </div>

        {/* Conversation footer */}
        <div className="px-5 py-3 border-t border-white/5">
          <div className="maya-section-label mb-2">{t.conversation[lang]}</div>
          {hasConversation ? (
            <div className="space-y-1.5">
              {conversation.slice(-3).map((m, i) => (
                <ConversationRow key={i} msg={m} />
              ))}
            </div>
          ) : (
            <div className="text-[11px] text-white/45">{t.noConversation[lang]}</div>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="maya-section-label mb-1.5">{title}</div>
      {children}
    </div>
  );
}

function Stat({ label, value, valueClass }: { label?: string; value: string; valueClass?: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      {label && <span className="text-white/45 uppercase tracking-wider">{label}</span>}
      <span className={`text-white/90 ${valueClass ?? ""}`}>{value}</span>
    </div>
  );
}

function ConversationRow({ msg }: { msg: WhatsAppMessage }) {
  const isOut = msg.direction === "out";
  const prefixClass = isOut ? "text-brand-200" : "text-white/55";
  return (
    <div className="text-[11.5px] leading-snug flex items-baseline gap-1.5">
      <span className={`font-medium shrink-0 ${prefixClass}`}>{msg.prefix}:</span>
      <span className="text-white/80 truncate flex-1">{msg.body}</span>
      <span className="text-[10px] text-white/40 shrink-0">{msg.ago}</span>
    </div>
  );
}
