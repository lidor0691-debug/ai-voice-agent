"use client";

import Link from "next/link";
import type { VoiceCall } from "../watch-mock";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";

interface VoiceCallsPanelProps {
  calls: VoiceCall[];
  lang: Lang;
}

export function VoiceCallsPanel({ calls, lang }: VoiceCallsPanelProps) {
  const liveCount = calls.filter(c => c.live).length;

  if (calls.length === 0) {
    return (
      <>
        <div className="maya-card__head">
          <div className="maya-card__title">{watchStrings.rails.voiceCalls[lang]}</div>
          <span className="maya-card__action">
            {lang === "he" ? "אף שיחה לא פעילה" : "no live calls"}
          </span>
        </div>
        <div className="maya-stat__l" style={{ fontStyle: "italic", marginBottom: 8 }}>
          {lang === "he" ? "מאיה מקשיבה. שיחות יוצגו כאן בזמן אמת." : "Maya is listening. Calls appear here in real time."}
        </div>
        <div style={{ flex: 1, minHeight: 0 }}>
          <div className="maya-ghost-row">
            <span className="maya-ghost-row__avatar" aria-hidden />
            <span>{lang === "he" ? "שיחה נכנסת תופיע כאן" : "Incoming call will appear here"}</span>
            <span className="maya-ghost-row__meta">— :—</span>
          </div>
          <div className="maya-ghost-row">
            <span className="maya-ghost-row__avatar" aria-hidden />
            <span>{lang === "he" ? "שיחת מעקב אוטומטית" : "Auto follow-up call"}</span>
            <span className="maya-ghost-row__meta">— :—</span>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="maya-card__head">
        <div className="maya-card__title">
          {liveCount > 0 && <span className="maya-card__live-dot" aria-hidden />}
          {watchStrings.rails.voiceCalls[lang]}
        </div>
        <span className="maya-card__action">
          {liveCount > 0
            ? (lang === "he" ? `${liveCount} עכשיו` : `${liveCount} now`)
            : (lang === "he" ? "אין פעילות" : "no live")}
        </span>
      </div>

      <div className="maya-list">
        {calls.map(c => {
          const initials = c.who
            .split(" ")
            .map(p => p[0])
            .slice(0, 2)
            .join("");
          return (
            <div key={c.id} className="maya-comm-row">
              <span className="maya-comm-row__avatar" aria-hidden>{initials}</span>
              <div style={{ minWidth: 0 }}>
                <div className="maya-comm-row__name" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  {c.live && <span className="maya-comm-row__live-dot" aria-hidden />}
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.who}</span>
                </div>
                <div className="maya-comm-row__sub">{c.meta} · {c.agent}</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className="maya-wave" style={{ color: "var(--gold-2)" }}>
                  <i style={{ height: 6 }} /><i style={{ height: 12 }} /><i style={{ height: 8 }} /><i style={{ height: 14 }} /><i style={{ height: 10 }} />
                </span>
                <span className="maya-comm-row__meta tnum">{c.duration}</span>
              </div>
            </div>
          );
        })}
      </div>
      <div className="maya-card__viewall">
        <span className="count">{calls.length} {lang === "he" ? "סה״כ" : "total"}</span>
        <Link href="/home/calls">{lang === "he" ? "כל השיחות ←" : "All calls →"}</Link>
      </div>
    </>
  );
}
