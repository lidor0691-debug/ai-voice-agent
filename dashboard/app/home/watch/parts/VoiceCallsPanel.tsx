"use client";

import { Phone } from "lucide-react";
import type { VoiceCall } from "../watch-mock";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";

interface VoiceCallsPanelProps {
  calls: VoiceCall[];
  lang: Lang;
}

export function VoiceCallsPanel({ calls, lang }: VoiceCallsPanelProps) {
  const liveCount = calls.filter(c => c.live).length;
  return (
    <div className="card bg-surface-2/55 border border-border-subtle rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Phone size={12} className="text-brand-200" />
        <span className="maya-section-label">{watchStrings.rails.voiceCalls[lang]}</span>
        <span className="ms-auto text-[10px] text-white/45">{liveCount} {lang === "he" ? "פעילות" : "live"}</span>
      </div>
      <div className="flex flex-col divide-y divide-white/5">
        {calls.map(c => (
          <div key={c.id} className="py-2.5 flex items-center gap-3">
            <span className="maya-live-dot" aria-hidden />
            <div className="min-w-0 flex-1">
              <div className="text-[13px] text-white/90 truncate">{c.who}</div>
              <div className="text-[11px] text-white/50 truncate">{c.meta} · {c.agent}</div>
            </div>
            <div className="flex items-center gap-2">
              <span className="maya-wave text-brand-200">
                <i style={{ height: 6 }} /><i style={{ height: 12 }} /><i style={{ height: 8 }} /><i style={{ height: 14 }} /><i style={{ height: 10 }} />
              </span>
              <span className="text-[11px] text-white/65 tabular-nums w-12 text-end">{c.duration}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
