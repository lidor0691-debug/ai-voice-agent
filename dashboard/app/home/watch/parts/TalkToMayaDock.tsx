"use client";

import { Mic, Send, Sparkles } from "lucide-react";
import { useRef, useState } from "react";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";

interface TalkToMayaDockProps {
  prompts: string[];
  lang: Lang;
  onSend?: (text: string) => void;
  /** Stage 9B — when present, renders the "הצע לי עדכון חכם" chip that
   *  populates the input with this draft text instead of submitting it.
   *  The parent (Watch.tsx) typically passes hero.suggestedMessage with
   *  hero.action as a fallback; undefined hides the chip entirely. */
  suggestionText?: string;
}

export function TalkToMayaDock({ prompts, lang, onSend, suggestionText }: TalkToMayaDockProps) {
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const t = watchStrings.dock;

  function send() {
    const v = text.trim();
    if (!v) return;
    onSend?.(v);
    setText("");
  }

  // Stage 9B — fill the input with the current hero's suggested draft and
  // hand focus to it. Pure local state mutation: no network, no submission,
  // no action recording. Replaces existing input text by design (this is a
  // "draft this for me" affordance, not an append).
  function applySuggestion() {
    if (!suggestionText) return;
    setText(suggestionText);
    inputRef.current?.focus();
  }

  return (
    <div className="
      sticky bottom-4 mx-auto max-w-[920px] w-full
      bg-surface-2/85 backdrop-blur-xl
      border border-border-strong rounded-2xl
      shadow-[0_24px_60px_-24px_rgba(0,0,0,0.7)]
      px-4 py-3
    ">
      <div className="flex items-center gap-2 mb-2.5 overflow-x-auto pb-1">
        <Sparkles size={11} className="text-brand-200 shrink-0" />
        <span className="maya-section-label shrink-0 me-1">{t.suggestions[lang]}</span>
        {suggestionText && (
          <button
            type="button"
            onClick={applySuggestion}
            className="shrink-0 px-3 h-7 rounded-full bg-white/5 hover:bg-white/10 border border-border-subtle text-[11px] text-white/75"
          >
            {t.smartSuggest[lang]}
          </button>
        )}
        {prompts.map((p, i) => (
          <button
            key={i}
            onClick={() => onSend?.(p)}
            className="shrink-0 px-3 h-7 rounded-full bg-white/5 hover:bg-white/10 border border-border-subtle text-[11px] text-white/75"
          >
            {p}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <button
          aria-label={watchStrings.dock.listening[lang]}
          className="w-10 h-10 rounded-xl bg-brand-500/15 hover:bg-brand-500/25 ring-1 ring-brand-400/25 grid place-items-center text-brand-200"
        >
          <Mic size={16} />
        </button>
        <input
          ref={inputRef}
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => e.key === "Enter" && send()}
          placeholder={t.placeholder[lang]}
          className="input-base flex-1 h-10 px-3 rounded-xl bg-surface-1/80 border border-border-subtle text-[13px] text-white placeholder:text-white/35 focus:outline-none focus:ring-1 focus:ring-brand-400/40"
        />
        <button
          onClick={send}
          aria-label="Send"
          className="w-10 h-10 rounded-xl bg-brand-500 hover:bg-brand-400 grid place-items-center text-white"
        >
          <Send size={16} className="rtl:rotate-180" />
        </button>
      </div>
    </div>
  );
}
