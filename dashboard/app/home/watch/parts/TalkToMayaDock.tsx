"use client";

import { Check, Copy, Eye, Mic, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { HeroRecommendation } from "../watch-mock";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";
import { SendPreviewModal } from "./SendPreviewModal";

interface TalkToMayaDockProps {
  prompts: string[];
  lang: Lang;
  onSend?: (text: string) => void;
  /** Stage 9B — when present, renders the "הצע לי עדכון חכם" chip that
   *  populates the input with this draft text instead of submitting it.
   *  The parent (Watch.tsx) typically passes hero.suggestedMessage with
   *  hero.action as a fallback; undefined hides the chip entirely. */
  suggestionText?: string;
  /** Stage 10A — current hero used by the Send Preview modal (lead name,
   *  phone, status label). When absent (quiet/failed/empty hero), the
   *  preview button is hidden because there's no real lead context to
   *  preview against. */
  hero?: HeroRecommendation;
}

export function TalkToMayaDock({ prompts, lang, onSend, suggestionText, hero }: TalkToMayaDockProps) {
  const [text, setText] = useState("");
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const t = watchStrings.dock;

  // Stage 10A — auto-close the preview modal when the underlying hero
  // changes (e.g. router.refresh() lands a new decision after an act/undo
  // elsewhere). Prevents the modal from showing stale lead context for a
  // draft that no longer matches the operator's current hero.
  useEffect(() => {
    setPreviewOpen(false);
  }, [hero?.id]);

  // Stage 9C — auto-revert the success indicator after a brief moment so
  // the icon swaps back to Copy. Cleanup cancels the timer on unmount or
  // when copied flips back early (e.g. a second copy click).
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(timer);
  }, [copied]);

  // Stage 9C — copy the trimmed input text to the clipboard. NOT a send.
  // No network, no AI, no action recording, no Twilio. Input contents stay
  // intact so the operator can paste, edit, copy again, or hand-edit
  // before pasting elsewhere.
  async function handleCopy() {
    const v = text.trim();
    if (!v) return;
    setCopyError(false);
    try {
      await navigator.clipboard.writeText(v);
      setCopied(true);
    } catch {
      setCopyError(true);
    }
  }

  // Stage 9B — fill the input with the current hero's suggested draft and
  // hand focus to it. Pure local state mutation: no network, no submission,
  // no action recording. Replaces existing input text by design (this is a
  // "draft this for me" affordance, not an append).
  function applySuggestion() {
    if (!suggestionText) return;
    setText(suggestionText);
    setCopied(false);    // reset success indicator when a fresh draft lands
    setCopyError(false);
    inputRef.current?.focus();
  }

  return (
    <>
    <div className="
      sticky bottom-4 mx-auto max-w-[920px] w-full
      bg-[#FFFCF6]/85 backdrop-blur-xl
      border border-border-strong rounded-2xl
      shadow-[0_24px_60px_-24px_rgba(0,0,0,0.7)]
      px-4 py-3
    ">
      <div className="flex items-center gap-2 mb-2.5 overflow-x-auto pb-1">
        <Sparkles size={11} className="text-[#A8884B] shrink-0" />
        <span className="maya-section-label shrink-0 me-1">{t.suggestions[lang]}</span>
        {suggestionText && (
          <button
            type="button"
            onClick={applySuggestion}
            className="shrink-0 px-3 h-7 rounded-full bg-[#0B1714]/[0.05] hover:bg-[#0B1714]/[0.08] border border-border-subtle text-[11px] text-[#0B1714]/75"
          >
            {t.smartSuggest[lang]}
          </button>
        )}
        {prompts.map((p, i) => (
          <button
            key={i}
            onClick={() => onSend?.(p)}
            className="shrink-0 px-3 h-7 rounded-full bg-[#0B1714]/[0.05] hover:bg-[#0B1714]/[0.08] border border-border-subtle text-[11px] text-[#0B1714]/75"
          >
            {p}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <button
          aria-label={watchStrings.dock.listening[lang]}
          className="w-10 h-10 rounded-xl bg-[#12372D]/15 hover:bg-[#12372D]/25 ring-1 ring-[#C9A66B]/25 grid place-items-center text-[#A8884B]"
        >
          <Mic size={16} />
        </button>
        <input
          ref={inputRef}
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleCopy()}
          placeholder={t.placeholder[lang]}
          className="input-base flex-1 h-10 px-3 rounded-xl bg-[#FFFCF6]/80 border border-border-subtle text-[13px] text-[#0B1714] placeholder:text-[#0B1714]/35 focus:outline-none focus:ring-1 focus:ring-[#C9A66B]/40"
        />
        {/* Stage 10A — preview button. Visible only when there's a draft AND
            a real hero — quiet/failed states have no lead context worth
            previewing. Secondary visual weight (ghost) keeps the Stage 9C
            Copy button as the primary affordance. */}
        {Boolean(text.trim() && hero?.id) && (
          <button
            type="button"
            onClick={() => setPreviewOpen(true)}
            aria-label={t.preview[lang]}
            className="w-10 h-10 rounded-xl bg-[#0B1714]/[0.05] hover:bg-[#0B1714]/[0.08] ring-1 ring-border-subtle grid place-items-center text-[#0B1714]/75 hover:text-[#0B1714] transition-colors"
          >
            <Eye size={16} />
          </button>
        )}
        {/* Stage 9C — copy-to-clipboard, NOT send. Icon flips to Check during
            the brief success window. aria-label reflects current state so
            screen readers announce "הועתק" right after the click. */}
        <button
          type="button"
          onClick={handleCopy}
          disabled={!text.trim()}
          aria-label={copied ? t.copied[lang] : t.copy[lang]}
          className="w-10 h-10 rounded-xl bg-[#12372D] hover:bg-[#1F4A3D] disabled:bg-[#12372D]/40 disabled:cursor-not-allowed grid place-items-center text-[#0B1714] transition-colors"
        >
          {copied ? <Check size={16} /> : <Copy size={16} />}
        </button>
      </div>

      {(copied || copyError) && (
        <div
          role="status"
          aria-live="polite"
          className={`mt-1.5 text-[10px] flex items-center gap-1.5 ${
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
    </div>

    {previewOpen && hero && text.trim() && (
      <SendPreviewModal
        hero={hero}
        draftText={text}
        lang={lang}
        onClose={() => setPreviewOpen(false)}
      />
    )}
    </>
  );
}
