"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { HeroRecommendation, WhatsAppThread } from "../watch-mock";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";
import { HeroDetailsModal } from "./HeroDetailsModal";

interface HeroRecommendationProps {
  hero: HeroRecommendation;
  lang: Lang;
  whatsapp?: WhatsAppThread[];
  /** Number of additional pending decisions, shown as "+N more" below the CTA. */
  moreCount?: number;
  onApprove?: () => void;
  onDecline?: () => void;
}

export function HeroRecommendationCard({
  hero, lang, whatsapp, moreCount = 0, onApprove, onDecline,
}: HeroRecommendationProps) {
  const t = watchStrings.hero;
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const matchingThread = useMemo<WhatsAppThread | undefined>(() => {
    if (!hero.phone || !whatsapp || whatsapp.length === 0) return undefined;
    return whatsapp.find(th => th.phone === hero.phone);
  }, [hero.phone, whatsapp]);

  const canShowDetails = Boolean(hero.id);

  useEffect(() => {
    setPending(false);
    setError(null);
    setDetailsOpen(false);
  }, [hero.id]);

  const canAct = Boolean(hero.id) && !pending;

  async function handleApprove() {
    if (!hero.id || pending) return;
    setPending(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/home/watch/decisions/${encodeURIComponent(hero.id)}/act`,
        { method: "POST", cache: "no-store" },
      );
      if (!res.ok) {
        setError(t.actError[lang]);
        setPending(false);
        return;
      }
      onApprove?.();
      router.refresh();
    } catch {
      setError(t.actError[lang]);
      setPending(false);
    }
  }

  const initials = (hero.target || "M")
    .split(" ")
    .map(w => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("");

  // Quiet state — no actionable decision behind hero. Keep the rich card shell.
  if (!hero.id) {
    return (
      <section className="maya-decision maya-decision--quiet maya-fade-in" aria-label={t.title[lang]}>
        <div className="maya-decision__body">
          <div className="maya-decision__lead">
            <div className="maya-decision__avatar" aria-hidden>מ</div>
            <div className="maya-decision__lead-body">
              <div className="maya-decision__head">
                <h2 className="maya-decision__name" style={{ fontWeight: 400, fontStyle: "italic" }}>
                  {lang === "he" ? "אין החלטה דחופה כרגע" : "No urgent decision"}
                </h2>
                <span className="maya-decision__when">
                  {lang === "he" ? "מאיה ערה" : "Maya on watch"}
                </span>
              </div>
              <p className="maya-decision__quote">{hero.headline}</p>
            </div>
          </div>
          <div className="maya-decision__recommend">
            <span className="maya-decision__reco-tag">
              {lang === "he" ? "מצב" : "Status"}
            </span>
            <h3 className="maya-decision__recommend-headline" style={{ color: "var(--ink-2)", fontStyle: "italic" }}>
              {hero.action && hero.action !== "—"
                ? hero.action
                : (lang === "he" ? "מאיה ממשיכה לעקוב אחר כל הפניות." : "Maya continues to monitor all leads.")}
            </h3>
          </div>
        </div>
      </section>
    );
  }

  const Arrow = lang === "he" ? ChevronLeft : ChevronRight;
  const quote = hero.suggestedMessage || hero.why[0] || hero.headline;
  const recommendationHeadline = hero.action && hero.action !== "—" ? hero.action : hero.headline;
  const ctaText = hero.action && hero.action !== "—" ? hero.action : t.primary[lang];

  return (
    <>
      <section className="maya-decision maya-fade-in" aria-label={t.title[lang]}>
        <div className="maya-decision__body">
          {/* Section eyebrow — business framing */}
          <span className="maya-decision__section-eyebrow">
            <span className="pulse" aria-hidden />
            {lang === "he" ? "דורש החלטה עכשיו" : "Needs your call"}
          </span>

          {/* Top row — avatar + name + business-framed value */}
          <div className="maya-decision__lead">
            <div className="maya-decision__avatar" aria-hidden>{initials || "M"}</div>
            <div className="maya-decision__lead-body">
              <div className="maya-decision__head">
                <h2 className="maya-decision__name">{hero.target}</h2>
                {hero.confidence != null && (
                  <span className="maya-decision__when">
                    {t.confidence[lang]} {hero.confidence}%
                  </span>
                )}
              </div>
              <div className="maya-decision__meta">
                {hero.value && (
                  <span>
                    <span className="maya-decision__meta__label">
                      {lang === "he" ? "כסף בסיכון" : "Money at risk"}
                    </span>
                    <strong>{hero.value}</strong>
                  </span>
                )}
                {hero.window && (
                  <span>
                    <span className="maya-decision__meta__label">
                      {lang === "he" ? "חלון פעולה" : "Window"}
                    </span>
                    <strong style={{ color: "var(--ink)", fontSize: 15 }}>{hero.window}</strong>
                  </span>
                )}
                {hero.impact && hero.impact !== hero.value && (
                  <span>
                    <span className="maya-decision__meta__label">
                      {lang === "he" ? "השפעה" : "Impact"}
                    </span>
                    <strong style={{ color: "var(--ink)", fontSize: 15 }}>{hero.impact}</strong>
                  </span>
                )}
                {hero.delivery && (
                  <span>
                    <span className="maya-decision__meta__label">
                      {lang === "he" ? "סטטוס" : "Status"}
                    </span>
                    <strong style={{
                      color: hero.delivery.tone === "warn" ? "var(--down)" : "var(--up)",
                      fontSize: 14,
                    }}>
                      {hero.delivery.label}
                    </strong>
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Quote — what the customer said */}
          <p className="maya-decision__quote">{quote}</p>

          {/* Recommendation — Maya's voice */}
          <div className="maya-decision__recommend">
            <span className="maya-decision__reco-tag">
              {lang === "he" ? "מאיה ממליצה" : "Maya recommends"}
            </span>
            <h3 className="maya-decision__recommend-headline">{recommendationHeadline}</h3>
          </div>
        </div>

        <button
          type="button"
          className="maya-decision__cta"
          onClick={handleApprove}
          disabled={!canAct}
        >
          <span className="maya-decision__cta-text">
            {pending ? t.primaryPending[lang] : ctaText}
          </span>
          <span className="maya-decision__cta-arrow" aria-hidden>
            <Arrow size={16} strokeWidth={2.4} />
          </span>
        </button>

        <p className="maya-decision__outcome">
          {lang === "he"
            ? <>אם תאשר — <strong>מאיה תשלח עכשיו</strong> ותעדכן את היומן ברגע שיהיה אישור.</>
            : <>If approved — <strong>Maya sends immediately</strong> and updates the calendar on reply.</>}
        </p>

        <div className="maya-decision__alt">
          <button
            type="button"
            onClick={() => setDetailsOpen(true)}
            disabled={!canShowDetails}
          >
            {t.secondary[lang]}
          </button>
          {onDecline && (
            <button type="button" onClick={onDecline} disabled={pending}>
              {t.decline[lang]}
            </button>
          )}
          {moreCount > 0 && (
            <span className="more">
              {lang === "he" ? `+${moreCount} החלטות פתוחות` : `+${moreCount} more open`}
            </span>
          )}
        </div>

        {error && (
          <div
            role="alert"
            style={{
              fontSize: 12, color: "var(--sienna)",
              display: "flex", alignItems: "center", gap: 8,
              marginTop: 2,
            }}
          >
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--sienna)" }} />
            <span>{error}</span>
          </div>
        )}
      </section>

      {detailsOpen && canShowDetails && (
        <HeroDetailsModal
          hero={hero}
          thread={matchingThread}
          lang={lang}
          onClose={() => setDetailsOpen(false)}
        />
      )}
    </>
  );
}
