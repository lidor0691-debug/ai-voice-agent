"use client";

import Link from "next/link";
import type { LeadStage } from "../watch-mock";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";

interface LeadPipelineProps {
  stages: LeadStage[];
  lang: Lang;
}

export function LeadPipeline({ stages, lang }: LeadPipelineProps) {
  const total = stages.reduce((s, x) => s + x.n, 0);

  // Even when total is zero, render the funnel stages so the panel keeps
  // structural mass. Real data (zeros are real). Add a small italic note.
  return (
    <>
      <div className="maya-card__head">
        <div className="maya-card__title">
          {total > 0 && <span className="maya-card__live-dot" aria-hidden />}
          {watchStrings.rails.leadPipeline[lang]}
        </div>
        <span className="maya-card__action">
          {total > 0
            ? (lang === "he" ? `${total} סה״כ` : `${total} total`)
            : (lang === "he" ? "אין פעילים" : "no active")}
        </span>
      </div>

      <div className="maya-funnel">
        {stages.map(s => {
          const isDown = false; // Lead funnel stages are all forward-state, no down tone.
          return (
            <div key={s.stage} className={`maya-funnel-row ${isDown ? "is-down" : ""}`}>
              <div className="maya-funnel-row__label">
                <div className="name">{s.stage}</div>
                <div className="sub">
                  {lang === "he" ? `${Math.round(s.pct * 100)}% מהשלב הקודם` : `${Math.round(s.pct * 100)}% of previous`}
                </div>
              </div>
              <div className="maya-funnel-row__bar">
                <i style={{ width: `${Math.max(4, Math.round(s.pct * 100))}%` }} />
              </div>
              <div className="maya-funnel-row__val">
                <span className="v tnum">{s.n}</span>
              </div>
            </div>
          );
        })}
      </div>
      <div className="maya-card__viewall">
        <span className="count">{total} {lang === "he" ? "סה״כ" : "total"}</span>
        <Link href="/home/leads">{lang === "he" ? "כל הלידים ←" : "All leads →"}</Link>
      </div>
    </>
  );
}
