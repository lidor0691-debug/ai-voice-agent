"use client";

import { HeroRecommendationCard } from "./parts/HeroRecommendation";
import { ActivityRail } from "./parts/ActivityRail";
import { VoiceCallsPanel } from "./parts/VoiceCallsPanel";
import { WhatsAppPanel } from "./parts/WhatsAppPanel";
import { LeadPipeline } from "./parts/LeadPipeline";
import { TalkToMayaDock } from "./parts/TalkToMayaDock";
import { HomeNavRail } from "../_shared/HomeNavRail";
import type { HandledToday, Kpi, VoiceCall, WatchData, WhatsAppThread } from "./watch-mock";
import type { Lang } from "../_shared/home-strings";

interface WatchProps {
  data: WatchData;
  lang: Lang;
  onApprove?: () => void;
  onDecline?: () => void;
  onAsk?: (text: string) => void;
}

export function Watch({ data, lang, onApprove, onDecline, onAsk }: WatchProps) {
  const suggestionText =
    data.hero.suggestedMessage ||
    (data.hero.action && data.hero.action !== "—" ? data.hero.action : undefined);

  const firstName = data.user.name.split(" ")[0];

  // Recovered amount (v1 estimate): handled.count × ₪850 placeholder.
  // Wire to real attribution endpoint when available.
  const AVG_TICKET = 850;
  const recoveredAmount = data.handledToday.count * AVG_TICKET;
  const recoveredLabel = recoveredAmount > 0
    ? `₪${recoveredAmount.toLocaleString(lang === "he" ? "he-IL" : "en-US")}`
    : null;

  const tickerKpis = data.kpis.filter(k => k.key !== "rev").slice(0, 4);

  const now = new Date();
  const dateLabel = now.toLocaleDateString(lang === "he" ? "he-IL" : "en-US", {
    weekday: "long", day: "numeric", month: "long",
  });
  const timeLabel = now.toLocaleTimeString(lang === "he" ? "he-IL" : "en-US", {
    hour: "2-digit", minute: "2-digit",
  });

  return (
    <>
      {/* Narrow viewport fallback */}
      <div className="sm:hidden absolute inset-0 grid place-items-center px-6 text-center maya-hebrew">
        <div className="space-y-2">
          <div className="maya-section-label">Maya · Watch</div>
          <p className="text-[#0B1714]/85 text-sm leading-relaxed">
            {lang === "he" ? "מסך Maya Watch מותאם כרגע לדסקטופ רחב" : "Maya Watch is desktop-only for now"}
          </p>
        </div>
      </div>

      <div className="hidden sm:block maya-app">
        <HomeNavRail lang={lang} active="watch" user={data.user} />

        <main className="maya-canvas maya-fade-in">
          {/* ── Vigil hairline ─────────────────────────────────── */}
          <div className="maya-vigil" aria-hidden>
            <span className="maya-vigil__pulse" />
          </div>

          {/* ── Byline — newspaper masthead ────────────────────── */}
          <div className="maya-byline" aria-hidden>
            <span className="maya-byline__label">
              {lang === "he" ? "מאיה" : "Maya"} · {dateLabel} · {timeLabel}
            </span>
          </div>

          {/* ── BRIEFING SURFACE — one large premium card ─────── */}
          <section className="maya-briefing-zone" aria-label={lang === "he" ? "תדריך הבוקר" : "Morning briefing"}>
            <header className="maya-briefing-zone__head">
              <h1 className="maya-briefing-zone__greet">
                {lang === "he" ? <>בוקר טוב, <strong>{firstName}</strong>. </> : <>Good morning, <strong>{firstName}</strong>. </>}
                <Narrative
                  handledCount={data.handledToday.count}
                  recoveredLabel={recoveredLabel}
                  lang={lang}
                />
              </h1>
              <span className="maya-briefing-zone__eyebrow">
                <span className="dot" aria-hidden />
                {lang === "he" ? "מאיה מנטרת" : "Maya on watch"}
              </span>
            </header>

            <div className="maya-briefing-zone__body">
              <HeroRecommendationCard
                hero={data.hero}
                lang={lang}
                whatsapp={data.whatsapp}
                moreCount={Math.max(0, data.alerts.length - 1)}
                onApprove={onApprove}
                onDecline={onDecline}
              />

              <div className="maya-briefing-zone__followup">
                <div className="maya-briefing-zone__followup__block">
                  <div className="maya-briefing-zone__followup__title">
                    {lang === "he" ? "טופל על ידי מאיה הלילה" : "Handled by Maya overnight"}
                  </div>
                  <NightLog handled={data.handledToday} lang={lang} />
                </div>
                <div className="maya-briefing-zone__followup__block">
                  <div className="maya-briefing-zone__followup__title">
                    {lang === "he" ? "ממתינים למענה היום" : "Awaiting response today"}
                  </div>
                  <DayRhythm
                    kpis={data.kpis}
                    calls={data.calls}
                    whatsapp={data.whatsapp}
                    leads={data.leads}
                    handled={data.handledToday}
                    lang={lang}
                    recoveredLabel={recoveredLabel}
                  />
                </div>
              </div>
            </div>
          </section>

          {/* ── SYSTEM ZONE — compact KPIs + operational cards ── */}
          <div className="maya-section-rule" data-label={lang === "he" ? "המערכת" : "The System"} aria-hidden />

          <div className="maya-kpi-cards">
            {tickerKpis.map(k => <KpiCard key={k.key} kpi={k} lang={lang} />)}
          </div>

          <section className="maya-ops-row">
            <div className="maya-card">
              <VoiceCallsPanel calls={data.calls} lang={lang} />
            </div>
            <div className="maya-card">
              <WhatsAppPanel threads={data.whatsapp} lang={lang} />
            </div>
            <div className="maya-card">
              <LeadPipeline stages={data.leads} lang={lang} />
            </div>
            <div className="maya-card">
              <ActivityRail
                alerts={data.alerts}
                insights={data.insights}
                wins={data.wins}
                patterns={data.patterns}
                lang={lang}
              />
            </div>
          </section>

          {/* ── Talk-to-Maya dock — pinned strip ──────────────── */}
          <div className="maya-dock-strip">
            <div className="maya-dock">
              <TalkToMayaDock
                prompts={data.prompts}
                lang={lang}
                onSend={onAsk}
                suggestionText={suggestionText}
                hero={data.hero}
              />
            </div>
          </div>
        </main>
      </div>
    </>
  );
}

/* ── Greeting narrative (Maya's voice, 1 sentence) ───────────── */
function Narrative({
  handledCount, recoveredLabel, lang,
}: { handledCount: number; recoveredLabel: string | null; lang: Lang }) {
  if (handledCount === 0) {
    return <>{lang === "he" ? "לילה שקט. מאיה ערה ומנטרת." : "Quiet night. Maya is on watch."}</>;
  }
  if (lang === "he") {
    return (
      <>
        לילה שקט. מאיה ענתה ל-<strong>{handledCount}</strong>{" "}
        {handledCount === 1 ? "פנייה" : "פניות"}
        {recoveredLabel && <>. הצילה <span className="recovered">{recoveredLabel}</span> השבוע</>}.
      </>
    );
  }
  return (
    <>
      Quiet night. Maya handled <strong>{handledCount}</strong>{" "}
      {handledCount === 1 ? "lead" : "leads"}
      {recoveredLabel && <>. Saved <span className="recovered">{recoveredLabel}</span> this week</>}.
    </>
  );
}

/* ── Night receipts ────────────────────────────────────────────
   Renders ✓ rows from handledToday.recent. Title comes from the
   parent followup block, so this is just the content. */
function NightLog({ handled, lang }: { handled: HandledToday; lang: Lang }) {
  if (!handled.recent || handled.recent.length === 0) {
    return (
      <div className="maya-nightlog__empty">
        {lang === "he"
          ? "לילה שקט. מאיה ערה ולא היה צורך בפעולה."
          : "Quiet night. Maya is on watch — no action needed."}
      </div>
    );
  }
  return (
    <div className="maya-nightlog">
      {handled.recent.slice(0, 4).map((item, i) => (
        <div key={`${item.phone}-${i}`} className="maya-nightlog__row">
          <span className="maya-nightlog__check" aria-hidden>✓</span>
          <span>
            <strong>{item.leadName}</strong>
            {" — "}
            {item.statusLabel}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ── Rhythm prose — operational numbers as a sentence ──────────
   Title comes from the parent followup block. Two lines: appointments
   prose on top, recovered + ops counts on bottom. */
function DayRhythm({
  kpis, calls, whatsapp, leads, handled: _handled, lang, recoveredLabel,
}: {
  kpis: Kpi[];
  calls: VoiceCall[];
  whatsapp: WhatsAppThread[];
  leads: { n: number }[];
  handled: HandledToday;
  lang: Lang;
  recoveredLabel: string | null;
}) {
  const liveCalls = calls.filter(c => c.live).length;
  const unread = whatsapp.filter(t => t.unread).length;
  const totalLeads = leads.reduce((s, x) => s + x.n, 0);
  const callsKpi = kpis.find(k => k.key === "calls");
  const apptStr = callsKpi?.value ?? totalLeads.toString();

  return (
    <p className="maya-rhythm">
      {lang === "he" ? (
        <>
          <span className="num">{apptStr}</span> פניות טופלו ·{" "}
          <span className="num">{totalLeads}</span> לידים בצינור ·{" "}
          <span className="num">{liveCalls}</span> {liveCalls === 1 ? "שיחה פעילה" : "שיחות פעילות"}.
          <br />
          {recoveredLabel && <><span className="recovered-inline">{recoveredLabel}</span> הוחזר השבוע · </>}
          <span className="num">{unread}</span> {unread === 1 ? "הודעה" : "הודעות"} ב-WhatsApp ממתינות.
        </>
      ) : (
        <>
          <span className="num">{apptStr}</span> handled ·{" "}
          <span className="num">{totalLeads}</span> in pipeline ·{" "}
          <span className="num">{liveCalls}</span> live {liveCalls === 1 ? "call" : "calls"}.
          <br />
          {recoveredLabel && <><span className="recovered-inline">{recoveredLabel}</span> recovered this week · </>}
          <span className="num">{unread}</span> WhatsApp {unread === 1 ? "thread" : "threads"} waiting.
        </>
      )}
    </p>
  );
}

/* ── KPI card — full premium card with honest direction baseline ─ */
function KpiCard({ kpi, lang }: { kpi: Kpi; lang: Lang }) {
  const deltaText = kpi.delta?.trim() ?? "";
  const hasDelta = deltaText !== "" && deltaText !== "—" && deltaText !== "-" && deltaText !== "0" && deltaText !== "0%";

  let dir: "up" | "down" | "flat";
  if (kpi.dir === "down" || deltaText.startsWith("-") || deltaText.startsWith("−")) dir = "down";
  else if (kpi.dir === "flat" || !hasDelta) dir = "flat";
  else dir = "up";

  const arrow = dir === "down" ? "↓" : dir === "up" ? "↑" : "→";
  const deltaClean = deltaText.replace(/^[+\-−]/, "").trim();

  // Honest direction baseline — a gentle wave that signals direction only.
  // No magnitude, no time series. Curve shape is the same per direction,
  // not derived from any phantom data. Same wave for "up" cell regardless
  // of which KPI it represents.
  const W = 120, H = 22;
  const wave = dir === "up"
    ? `M 0 ${H - 4} C ${W * 0.3} ${H - 4}, ${W * 0.55} ${H - 12}, ${W} 4`
    : dir === "down"
    ? `M 0 4 C ${W * 0.3} 4, ${W * 0.55} ${H - 12}, ${W} ${H - 4}`
    : `M 0 ${H / 2} L ${W} ${H / 2}`;

  return (
    <div className="maya-kpi">
      <div className="maya-kpi__label">{kpi.label}</div>
      <div className="maya-kpi__row">
        <div className="maya-kpi__value tnum">{kpi.value || "0"}</div>
        {hasDelta ? (
          <div className={`maya-kpi__delta ${dir}`}>
            <span aria-hidden>{arrow}</span> {deltaClean}
          </div>
        ) : (
          <div className="maya-kpi__delta none">
            {lang === "he" ? "ללא שינוי" : "no change"}
          </div>
        )}
      </div>
      <div className={`maya-kpi__indicator dir-${dir}`} aria-hidden>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
          <path d={wave} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      </div>
    </div>
  );
}
