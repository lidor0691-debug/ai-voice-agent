"use client";

import { useEffect, useState } from "react";
import { Check, Copy, X } from "lucide-react";
import type { HeroRecommendation } from "../watch-mock";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";

/** Map decision_status enum → Hebrew label. Mirrors HeroDetailsModal so the
 *  operator sees the same wording across surfaces. */
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

interface SendPreviewModalProps {
  hero: HeroRecommendation;
  /** The operator's current dock input — what would be sent if a real send
   *  flow existed. Read-only here; the modal does not mutate the dock. */
  draftText: string;
  lang: Lang;
  onClose: () => void;
}

export function SendPreviewModal({ hero, draftText, lang, onClose }: SendPreviewModalProps) {
  const t = watchStrings.sendPreview;
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);

  // Esc closes — same pattern as HeroDetailsModal.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Auto-revert success indicator after 1.5s. Cleanup cancels timer if the
  // modal closes early or the user clicks copy again before the window ends.
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(timer);
  }, [copied]);

  async function handleCopy() {
    const v = draftText.trim();
    if (!v) return;
    setCopyError(false);
    try {
      await navigator.clipboard.writeText(v);
      setCopied(true);
    } catch {
      setCopyError(true);
    }
  }

  const statusLabel = statusLabelHe(hero.status);

  return (
    <div
      className="fixed inset-0 z-[100] grid place-items-center bg-[#0B1714]/35 backdrop-blur-sm maya-fade-in"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-full max-w-md mx-4 max-h-[85vh] overflow-y-auto bg-[#FFFCF6]/95 backdrop-blur-xl border border-border-strong rounded-2xl shadow-[0_30px_80px_-20px_rgba(0,0,0,0.7)]"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#E6DCCB]/70">
          <div className="min-w-0">
            <div className="text-[14px] text-[#0B1714]/90 truncate">{hero.target}</div>
            <div className="text-[11px] text-[#0B1714]/50 mt-0.5 flex items-center gap-2">
              {hero.phone && (
                <span dir="ltr" className="tabular-nums [unicode-bidi:isolate]">
                  {hero.phone}
                </span>
              )}
              {hero.phone && hero.status && <span className="text-[#0B1714]/30">·</span>}
              {hero.status && <span>{statusLabel}</span>}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t.close[lang]}
            className="w-8 h-8 grid place-items-center rounded-lg text-[#0B1714]/55 hover:bg-[#0B1714]/[0.05] hover:text-[#0B1714]/85 focus:outline-none focus:ring-1 focus:ring-[#C9A66B]/40 shrink-0"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-3">
          {/* Warning row — three layers of "not sent" signaling start here */}
          <div
            role="status"
            className="flex items-center gap-1.5 text-[12px] text-amber-300/90"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
            <span className="truncate">{t.warning[lang]}</span>
          </div>

          {/* Draft block */}
          <div>
            <div className="maya-section-label mb-1.5">{t.draftLabel[lang]}</div>
            <div className="rounded-xl border border-[#E6DCCB] bg-[#0B1714]/[0.05] px-3 py-2.5 text-[12.5px] text-[#0B1714]/90 leading-snug whitespace-pre-wrap break-words">
              {draftText}
            </div>
          </div>

          {/* Copy success / error inline feedback (modal-local) */}
          {(copied || copyError) && (
            <div
              role="status"
              aria-live="polite"
              className={`text-[10px] flex items-center gap-1.5 ${
                copyError ? "text-amber-300/85" : "text-emerald-300/90"
              }`}
            >
              <span className={`w-1 h-1 rounded-full shrink-0 ${
                copyError ? "bg-amber-400" : "bg-emerald-400"
              }`} />
              <span className="truncate">
                {copyError ? t.copyError[lang] : t.copied[lang]}
              </span>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={handleCopy}
              aria-label={copied ? t.copied[lang] : t.copyButton[lang]}
              className="btn-primary flex items-center gap-2 px-4 h-9 rounded-lg bg-[#12372D] hover:bg-[#1F4A3D] text-[#0B1714] text-[13px] font-medium"
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
              <span>{copied ? t.copied[lang] : t.copyButton[lang]}</span>
            </button>
            <button
              type="button"
              onClick={onClose}
              className="btn-ghost px-3 h-9 rounded-lg text-[#0B1714]/75 hover:bg-[#0B1714]/[0.05] text-[13px]"
            >
              {t.close[lang]}
            </button>
          </div>
        </div>

        {/* Future hint */}
        <div className="px-5 py-3 border-t border-[#E6DCCB]/70 text-[10px] text-[#0B1714]/35">
          {t.futureHint[lang]}
        </div>
      </div>
    </div>
  );
}
