"use client";

import { useEffect, useState } from "react";
import { Bot, User, X, MessageCircle } from "lucide-react";
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
  const unreadCount = threads.filter(t => t.unread).length;

  useEffect(() => {
    if (!openId) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpenId(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openId]);

  if (threads.length === 0) {
    return (
      <>
        <div className="maya-card__head">
          <div className="maya-card__title">{watchStrings.rails.whatsapp[lang]}</div>
          <span className="maya-card__action">
            {lang === "he" ? "הכל נענה" : "all replied"}
          </span>
        </div>
        <div className="maya-stat__l" style={{ fontStyle: "italic", marginBottom: 8 }}>
          {lang === "he" ? "אין שיחות ממתינות. מאיה תענה אוטומטית כשתגיע פנייה." : "No pending threads. Maya will reply automatically."}
        </div>
        <div style={{ flex: 1, minHeight: 0 }}>
          <div className="maya-ghost-row">
            <span className="maya-ghost-row__avatar" aria-hidden />
            <span>{lang === "he" ? "הודעה נכנסת תופיע כאן" : "Incoming message will appear here"}</span>
            <span className="maya-ghost-row__meta">—</span>
          </div>
          <div className="maya-ghost-row">
            <span className="maya-ghost-row__avatar" aria-hidden />
            <span>{lang === "he" ? "מעקב פנייה אחרונה" : "Last-lead follow-up"}</span>
            <span className="maya-ghost-row__meta">—</span>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="maya-card__head">
        <div className="maya-card__title">
          {unreadCount > 0 && <span className="maya-card__live-dot" aria-hidden />}
          {watchStrings.rails.whatsapp[lang]}
        </div>
        <span className="maya-card__action">
          {unreadCount > 0
            ? (lang === "he" ? `${unreadCount} חדשות` : `${unreadCount} new`)
            : (lang === "he" ? "הכל נענה" : "all replied")}
        </span>
      </div>

      <div className="maya-list">
        {threads.map(t => (
          <ThreadRow key={t.id} thread={t} onOpen={() => setOpenId(t.id)} lang={lang} />
        ))}
      </div>
      <div className="maya-card__viewall">
        <span className="count">{threads.length} {lang === "he" ? "שיחות" : "threads"}</span>
        <button type="button" onClick={() => threads[0] && setOpenId(threads[0].id)}>
          {lang === "he" ? "פתח את כולן ←" : "Open all →"}
        </button>
      </div>

      {openThread && (
        <ThreadModal thread={openThread} onClose={() => setOpenId(null)} />
      )}
    </>
  );
}

function ThreadRow({ thread, onOpen, lang }: { thread: WhatsAppThread; onOpen: () => void; lang: Lang }) {
  const headerName = thread.leadName ?? thread.who;
  const initials = headerName.split(" ").map(p => p[0]).slice(0, 2).join("");
  const isAI = thread.by === "AI";

  return (
    <button
      type="button"
      onClick={onOpen}
      className="maya-comm-row"
      style={{ cursor: "pointer" }}
    >
      <span className={`maya-comm-row__avatar ${isAI ? "" : "tone-human"}`} aria-hidden>
        {isAI ? <Bot size={14} /> : initials || <User size={14} />}
      </span>
      <div style={{ minWidth: 0 }}>
        <div className="maya-comm-row__name" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
            {headerName}
          </span>
          {thread.unread && (
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--forest)" }} />
          )}
        </div>
        <div className="maya-comm-row__sub" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {thread.preview}
        </div>
        {thread.delivery && (
          <DeliveryLine delivery={thread.delivery} lang={lang} />
        )}
      </div>
      <span className="maya-comm-row__meta tnum">{thread.ago}</span>
    </button>
  );
}

function DeliveryLine({ delivery, lang: _lang }: { delivery: DeliveryInfo; lang: Lang }) {
  const tone = delivery.tone === "warn" ? "var(--down)" : delivery.tone === "ok" ? "var(--up)" : "var(--ink-3)";
  return (
    <div style={{ fontSize: 10, color: tone, marginTop: 4, display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 4, height: 4, borderRadius: "50%", background: tone }} />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
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
      className="fixed inset-0 z-[100] grid place-items-center bg-[#0B1714]/35 backdrop-blur-sm maya-fade-in"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-full max-w-md mx-4 max-h-[80vh] overflow-y-auto bg-[#FFFCF6]/95 backdrop-blur-xl border border-[#E6DCCB] rounded-2xl"
        style={{ boxShadow: "0 30px 80px -20px rgba(20,19,14,0.4)" }}
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#E6DCCB]">
          <div className="flex items-center gap-2 min-w-0">
            <MessageCircle size={14} className="text-[#A8884B] shrink-0" />
            <span className="text-[14px] text-[#0B1714] truncate">{headerName}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="סגור"
            className="w-8 h-8 grid place-items-center rounded-lg text-[#0B1714]/55 hover:bg-[#0B1714]/[0.05] hover:text-[#0B1714]/85"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          {messages.length === 0 && (
            <div className="text-[12px] text-[#0B1714]/45 text-center py-6">
              אין עדיין הודעות בשיחה זו.
            </div>
          )}
          {messages.map((m, i) => (
            <TimelineMessage key={i} msg={m} />
          ))}
        </div>

        {thread.staleFollowupNote ? (
          <div className="px-5 py-3 border-t border-[#E6DCCB] text-[11px] text-[#0B1714]/45">
            {thread.staleFollowupNote}
            {thread.delivery?.label && ` · ${thread.delivery.label}`}
          </div>
        ) : (
          thread.delivery && (
            <div className="px-5 py-3 border-t border-[#E6DCCB]">
              <DeliveryLine delivery={thread.delivery} lang="he" />
            </div>
          )
        )}
      </div>
    </div>
  );
}

function TimelineMessage({ msg }: { msg: WhatsAppMessage }) {
  const isOut = msg.direction === "out";
  const containerClass = isOut
    ? "bg-[rgba(15,76,58,0.06)] border-[rgba(15,76,58,0.18)]"
    : "bg-[#0B1714]/[0.04] border-[#E6DCCB]";
  const prefixClass = isOut ? "text-[#A8884B]" : "text-[#0B1714]/55";

  return (
    <div className={`rounded-xl border ${containerClass} px-3 py-2.5`}>
      <div className="flex items-baseline justify-between gap-2 mb-1">
        <span className={`text-[11px] font-medium ${prefixClass}`}>
          {msg.prefix}
        </span>
        <span className="text-[10px] text-[#0B1714]/40">{msg.ago}</span>
      </div>
      <div className="text-[12.5px] text-[#0B1714]/85 leading-snug whitespace-pre-wrap break-words">
        {msg.body}
      </div>
    </div>
  );
}
