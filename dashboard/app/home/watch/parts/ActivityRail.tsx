"use client";

import Link from "next/link";
import { AlertTriangle, Lightbulb, Trophy, Sparkles } from "lucide-react";
import type { Alert, Insight, Win, Pattern } from "../watch-mock";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";

interface ActivityRailProps {
  alerts: Alert[];
  insights: Insight[];
  wins: Win[];
  patterns: Pattern[];
  lang: Lang;
}

type FeedItem = {
  type: "alert" | "insight" | "win" | "pattern";
  title: string;
  sub: string;
  meta?: string;
  ago?: string;
};

export function ActivityRail({ alerts, insights, wins, patterns, lang }: ActivityRailProps) {
  const t = watchStrings.rails;

  // Merge all activity streams into one unified feed — matches reference's
  // "פעילות אחרונה" pattern. Order: alerts → wins → insights → patterns.
  const feed: FeedItem[] = [
    ...alerts.map<FeedItem>(a => ({ type: "alert", title: a.who, sub: a.body, ago: a.ago })),
    ...wins.map<FeedItem>(w => ({ type: "win", title: w.name, sub: w.desc, meta: w.value })),
    ...insights.map<FeedItem>(i => ({ type: "insight", title: i.head, sub: i.body, meta: `${Math.round(i.conf * 100)}%` })),
    ...patterns.map<FeedItem>(p => ({ type: "pattern", title: p.head, sub: p.body })),
  ];

  if (feed.length === 0) {
    return (
      <>
        <div className="maya-card__head">
          <div className="maya-card__title">{lang === "he" ? "טופל על ידי מאיה" : "Handled by Maya"}</div>
          <span className="maya-card__action">
            {lang === "he" ? "אין סיכונים" : "no risks"}
          </span>
        </div>
        <div className="maya-stat__l" style={{ fontStyle: "italic", marginBottom: 8 }}>
          {lang === "he" ? "הכל שקט. מאיה תתריע כאן ברגע שתזהה משהו." : "All quiet. Maya will surface anything she finds here."}
        </div>
        <div style={{ flex: 1, minHeight: 0 }}>
          <div className="maya-ghost-row">
            <span className="maya-ghost-row__avatar" aria-hidden />
            <span>{lang === "he" ? "התראה תופיע כאן" : "Alert will appear here"}</span>
            <span className="maya-ghost-row__meta">—</span>
          </div>
          <div className="maya-ghost-row">
            <span className="maya-ghost-row__avatar" aria-hidden />
            <span>{lang === "he" ? "תובנה חדשה תופיע כאן" : "New insight will appear here"}</span>
            <span className="maya-ghost-row__meta">—</span>
          </div>
          <div className="maya-ghost-row">
            <span className="maya-ghost-row__avatar" aria-hidden />
            <span>{lang === "he" ? "ניצחון או דפוס יסומן כאן" : "Win or pattern flagged here"}</span>
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
          {feed.length > 0 && <span className="maya-card__live-dot" aria-hidden />}
          {lang === "he" ? "טופל על ידי מאיה" : "Handled by Maya"}
        </div>
        <span className="maya-card__action">
          {feed.length} {lang === "he" ? "עדכונים" : "updates"}
        </span>
      </div>

      <div className="maya-list">
        {feed.map((item, i) => (
          <FeedRow key={i} item={item} lang={lang} />
        ))}
      </div>
      <div className="maya-card__viewall">
        <span className="count">{feed.length} {lang === "he" ? "עדכונים" : "updates"}</span>
        <Link href="/home/insights">{lang === "he" ? "כל הפעילות ←" : "All activity →"}</Link>
      </div>
    </>
  );
}

function FeedRow({ item, lang: _lang }: { item: FeedItem; lang: Lang }) {
  const iconMap = {
    alert:   { Icon: AlertTriangle, tone: "alert" as const },
    win:     { Icon: Trophy,        tone: "win" as const },
    insight: { Icon: Lightbulb,     tone: "message" as const },
    pattern: { Icon: Sparkles,      tone: "meeting" as const },
  };
  const { Icon, tone } = iconMap[item.type];

  return (
    <div className="maya-act-row">
      <div className={`maya-act-row__icon tone-${tone}`}>
        <Icon size={14} strokeWidth={1.7} />
      </div>
      <div style={{ minWidth: 0 }}>
        <div className="maya-act-row__title" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
          {item.title}
        </div>
        <div className="maya-act-row__sub">{item.sub}</div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
        {item.meta && (
          <span style={{
            fontFamily: "'Frank Ruhl Libre', serif",
            fontSize: 14,
            fontWeight: 500,
            color: item.type === "win" ? "var(--up)" : "var(--gold-2)",
            fontFeatureSettings: '"tnum"',
            lineHeight: 1,
          }}>
            {item.meta}
          </span>
        )}
        {item.ago && <span className="maya-act-row__time">{item.ago}</span>}
      </div>
    </div>
  );
}
