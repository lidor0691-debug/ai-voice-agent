"use client";

import { MessageCircle, Bot, User } from "lucide-react";
import type { WhatsAppThread } from "../watch-mock";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";

interface WhatsAppPanelProps {
  threads: WhatsAppThread[];
  lang: Lang;
}

export function WhatsAppPanel({ threads, lang }: WhatsAppPanelProps) {
  return (
    <div className="card bg-surface-2/55 border border-border-subtle rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <MessageCircle size={12} className="text-brand-200" />
        <span className="maya-section-label">{watchStrings.rails.whatsapp[lang]}</span>
      </div>
      <div className="flex flex-col divide-y divide-white/5">
        {threads.map(t => (
          <div key={t.id} className="py-2.5 flex items-start gap-3">
            <div className={`mt-0.5 w-7 h-7 rounded-full grid place-items-center text-[10px] ${t.by === "AI" ? "bg-brand-500/15 text-brand-200 ring-1 ring-brand-400/25" : "bg-white/10 text-white/70"}`}>
              {t.by === "AI" ? <Bot size={12} /> : <User size={12} />}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-2">
                <span className="text-[13px] text-white/90 truncate">{t.who}</span>
                {t.unread && <span className="w-1.5 h-1.5 rounded-full bg-brand-400" />}
                <span className="ms-auto text-[10px] text-white/40">{t.ago}</span>
              </div>
              <div className="text-[11px] text-white/55 truncate">{t.preview}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
