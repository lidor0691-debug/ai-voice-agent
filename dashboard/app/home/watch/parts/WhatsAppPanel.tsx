"use client";

import { useEffect, useState } from "react";
import { MessageCircle, Bot, User, X } from "lucide-react";
import type { WhatsAppThread, WhatsAppMessage, DeliveryInfo } from "../watch-mock";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";

interface WhatsAppPanelProps {
  threads: WhatsAppThread[];
  lang: Lang;
}

export function WhatsAppPanel({ threads, lang }: WhatsAppPanelProps) {
  const [openId, setOpenId] = useState<string | null>(null);
  const openThread = openId ? threads.find(t => t.id === openId) ?? null : null;

  // Esc closes the modal.
  useEffect(() => {
    if (!openId) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpenId(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openId]);

  return (
    <div className="card bg-surface-2/55 border border-border-subtle rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <MessageCircle size={12} className="text-brand-200" />
        <span className="maya-section-label">{watchStrings.rails.whatsapp[lang]}</span>
      </div>
      <div className="flex flex-col divide-y divide-white/5">
        {threads.map(t => (
          <ThreadRow key={t.id} thread={t} onOpen={() => setOpenId(t.id)} />
        ))}
      </div>

      {openThread && (
        <ThreadModal thread={openThread} onClose={() => setOpenId(null)} />
      )}
    </div>
  );
}

function ThreadRow({ thread, onOpen }: { thread: WhatsAppThread; onOpen: () => void }) {
  const headerName = thread.leadName ?? thread.who;
  const messages = thread.messages;
  const hasConversation = !!messages && messages.length > 0;

  return (
    <button
      type="button"
      onClick={onOpen}
      className="text-start py-2.5 flex items-start gap-3 w-full hover:bg-white/[0.03] focus:bg-white/[0.04] focus:outline-none rounded-md transition-colors"
    >
      <div className={`mt-0.5 w-7 h-7 rounded-full grid place-items-center text-[10px] shrink-0 ${
        thread.by === "AI"
          ? "bg-brand-500/15 text-brand-200 ring-1 ring-brand-400/25"
          : "bg-white/10 text-white/70"
      }`}>
        {thread.by === "AI" ? <Bot size={12} /> : <User size={12} />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-[13px] text-white/90 truncate">{headerName}</span>
          {thread.unread && <span className="w-1.5 h-1.5 rounded-full bg-brand-400" />}
          <span className="ms-auto text-[10px] text-white/40">{thread.ago}</span>
        </div>

        {hasConversation ? (
          <div className="mt-1 space-y-1">
            {messages!.map((m, i) => (
              <CompactMessage key={i} msg={m} />
            ))}
          </div>
        ) : (
          <div className="text-[11px] text-white/55 truncate">{thread.preview}</div>
        )}

        {thread.delivery && <DeliveryLine delivery={thread.delivery} />}
      </div>
    </button>
  );
}

function CompactMessage({ msg }: { msg: WhatsAppMessage }) {
  const prefixClass = msg.direction === "out" ? "text-brand-200" : "text-white/55";
  return (
    <div className="text-[11px] leading-snug truncate">
      <span className={`font-medium ${prefixClass}`}>{msg.prefix}: </span>
      <span className="text-white/75">{msg.body}</span>
    </div>
  );
}

function DeliveryLine({ delivery }: { delivery: DeliveryInfo }) {
  const tone = delivery.tone;
  const dotClass =
    tone === "ok"   ? "bg-emerald-400" :
    tone === "warn" ? "bg-amber-400"   :
                      "bg-white/35";
  const textClass =
    tone === "ok"   ? "text-emerald-300/85" :
    tone === "warn" ? "text-amber-300/90"   :
                      "text-white/45";
  return (
    <div className={`text-[10px] mt-1 flex items-center gap-1.5 ${textClass}`}>
      <span className={`w-1 h-1 rounded-full ${dotClass}`} />
      <span className="truncate">
        {delivery.label}
        {delivery.errorLabel && ` · ${delivery.errorLabel}`}
      </span>
    </div>
  );
}

// ── Modal ──────────────────────────────────────────────────────────────

function ThreadModal({ thread, onClose }: { thread: WhatsAppThread; onClose: () => void }) {
  const headerName = thread.leadName ?? thread.who;
  const messages = thread.messages ?? [];

  return (
    <div
      className="fixed inset-0 z-[100] grid place-items-center bg-black/60 backdrop-blur-sm maya-fade-in"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-full max-w-md mx-4 max-h-[80vh] overflow-y-auto bg-surface-2/95 backdrop-blur-xl border border-border-strong rounded-2xl shadow-[0_30px_80px_-20px_rgba(0,0,0,0.7)]"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/5">
          <div className="flex items-center gap-2 min-w-0">
            <MessageCircle size={14} className="text-brand-200 shrink-0" />
            <span className="text-[14px] text-white/90 truncate">{headerName}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="סגור"
            className="w-8 h-8 grid place-items-center rounded-lg text-white/55 hover:bg-white/5 hover:text-white/85 focus:outline-none focus:ring-1 focus:ring-brand-400/40"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          {messages.length === 0 && (
            <div className="text-[12px] text-white/45 text-center py-6">
              אין עדיין הודעות בשיחה זו.
            </div>
          )}
          {messages.map((m, i) => (
            <TimelineMessage key={i} msg={m} />
          ))}
        </div>

        {thread.delivery && (
          <div className="px-5 py-3 border-t border-white/5">
            <DeliveryLine delivery={thread.delivery} />
          </div>
        )}
      </div>
    </div>
  );
}

function TimelineMessage({ msg }: { msg: WhatsAppMessage }) {
  const isOut = msg.direction === "out";
  const containerClass = isOut
    ? "bg-brand-500/10 border-brand-400/20"
    : "bg-white/[0.04] border-white/10";
  const prefixClass = isOut ? "text-brand-200" : "text-white/55";

  return (
    <div className={`rounded-xl border ${containerClass} px-3 py-2.5`}>
      <div className="flex items-baseline justify-between gap-2 mb-1">
        <span className={`text-[11px] font-medium ${prefixClass}`}>
          {msg.prefix}
        </span>
        <span className="text-[10px] text-white/40">{msg.ago}</span>
      </div>
      <div className="text-[12.5px] text-white/85 leading-snug whitespace-pre-wrap break-words">
        {msg.body}
      </div>
    </div>
  );
}
