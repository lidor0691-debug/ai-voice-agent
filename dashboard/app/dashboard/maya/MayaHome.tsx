"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  ChevronRight,
  Command,
  CornerDownLeft,
  Eye,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import { useLanguage } from "@/context/language-context";
import type {
  Decision,
  MayaHomeData,
  Mission,
  OrbState,
  PaletteItem,
} from "./maya-home-mock";
import { HOME_STRINGS, type HomeLang, type HomeStrings } from "./maya-home-strings";

// ───────────────────────────────────────────────────────────────────
// Top-level
// ───────────────────────────────────────────────────────────────────
type Mode = "day" | "night";

export function MayaHome({ data }: { data: MayaHomeData }) {
  const { lang, setLang } = useLanguage();
  const homeLang: HomeLang = lang === "he" ? "he" : "en";
  const s = HOME_STRINGS[homeLang];
  const dir: "rtl" | "ltr" = homeLang === "he" ? "rtl" : "ltr";

  // Demo: day/night toggle (in production, derived from local time)
  const [mode, setMode] = useState<Mode>("day");

  // Decisions state — approving collapses cards
  const [decisions, setDecisions] = useState<Decision[]>(data.decisions);
  const [resolvedIds, setResolvedIds] = useState<string[]>([]);
  const [orbState, setOrbState] = useState<OrbState>("idle");

  // Command palette
  const [paletteOpen, setPaletteOpen] = useState(false);

  // Cmd-K listener
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const isModK = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k";
      if (isModK) {
        e.preventDefault();
        setPaletteOpen((p) => !p);
      } else if (e.key === "Escape" && paletteOpen) {
        setPaletteOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paletteOpen]);

  function approveDecision(id: string) {
    setOrbState("heard");
    window.setTimeout(() => setOrbState("working"), 220);
    window.setTimeout(() => {
      setResolvedIds((r) => [...r, id]);
      setDecisions((curr) => curr.filter((d) => d.id !== id));
      setOrbState("idle");
    }, 1200);
  }

  function overrideDecision(id: string) {
    // Prototype: same effect as approve, different label upstream
    approveDecision(id);
  }

  return (
    <div
      dir={dir}
      lang={homeLang}
      className={`relative flex-1 overflow-y-auto overflow-x-hidden bg-surface-0 text-white ${
        homeLang === "he" ? "maya-hebrew" : ""
      } ${mode === "night" ? "maya-night" : ""}`}
    >
      <SurfaceTexture mode={mode} />

      {mode === "day" ? (
        <DaySurface
          data={data}
          s={s}
          dir={dir}
          orbState={orbState}
          decisions={decisions}
          resolvedCount={resolvedIds.length}
          onApprove={approveDecision}
          onOverride={overrideDecision}
          onOpenPalette={() => setPaletteOpen(true)}
          lang={homeLang}
          setLang={setLang}
        />
      ) : (
        <NightSurface s={s} orbState="watching" />
      )}

      {/* Demo controls — fixed corner */}
      <DemoToggle s={s} mode={mode} setMode={setMode} />

      {/* Command palette */}
      {paletteOpen && (
        <CommandPalette
          s={s}
          items={data.paletteItems}
          onClose={() => setPaletteOpen(false)}
        />
      )}

      <SurfaceCss />
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// Day surface — primary home composition
// ───────────────────────────────────────────────────────────────────
function DaySurface({
  data,
  s,
  dir,
  orbState,
  decisions,
  resolvedCount,
  onApprove,
  onOverride,
  onOpenPalette,
  lang,
  setLang,
}: {
  data: MayaHomeData;
  s: HomeStrings;
  dir: "rtl" | "ltr";
  orbState: OrbState;
  decisions: Decision[];
  resolvedCount: number;
  onApprove: (id: string) => void;
  onOverride: (id: string) => void;
  onOpenPalette: () => void;
  lang: HomeLang;
  setLang: (l: "he" | "en") => void;
}) {
  return (
    <>
      <StatusStrip
        instruments={data.instruments}
        date={data.date}
        s={s}
        lang={lang}
        setLang={setLang}
        onOpenPalette={onOpenPalette}
      />

      <div className="relative z-[1] max-w-[1320px] mx-auto px-6 md:px-10 pt-7 pb-10">
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px] gap-7">
          {/* Briefing column */}
          <BriefingPanel
            data={data}
            s={s}
            orbState={orbState}
          />

          {/* Decisions column */}
          <DecisionsColumn
            decisions={decisions}
            s={s}
            resolvedCount={resolvedCount}
            onApprove={onApprove}
            onOverride={onOverride}
          />
        </div>

        <ActiveMissionsRow missions={data.missions} s={s} dir={dir} />
        <FooterChrome s={s} />
      </div>
    </>
  );
}

// ───────────────────────────────────────────────────────────────────
// Status Strip — peripheral OS-chrome state
// ───────────────────────────────────────────────────────────────────
function StatusStrip({
  instruments,
  date,
  s,
  lang,
  setLang,
  onOpenPalette,
}: {
  instruments: MayaHomeData["instruments"];
  date: string;
  s: HomeStrings;
  lang: HomeLang;
  setLang: (l: "he" | "en") => void;
  onOpenPalette: () => void;
}) {
  const [now, setNow] = useState(() => new Date(date));
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(id);
  }, []);

  const dateLabel = now.toLocaleDateString(lang === "he" ? "he-IL" : "en-US", {
    weekday: "short",
    day: "2-digit",
    month: "short",
  }).toUpperCase();
  const timeLabel = now.toLocaleTimeString(lang === "he" ? "he-IL" : "en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="sticky top-0 z-[2] backdrop-blur-md bg-surface-0/85 border-b border-white/[0.05]">
      <div className="max-w-[1320px] mx-auto h-[44px] px-6 md:px-10 flex items-center gap-5 text-[11px] font-mono">
        {/* Left: date / time */}
        <div className="flex items-center gap-3 text-white/45">
          <span className="tracking-[0.16em]">{dateLabel}</span>
          <span className="text-white/15">·</span>
          <span className="tabular-nums text-white/70">{timeLabel}</span>
        </div>

        <span className="text-white/10">│</span>

        {/* Instruments */}
        <Instrument
          icon={Activity}
          tone="violet"
          value={instruments.inFlight.toString()}
          label={s.inFlight}
        />
        <Instrument
          icon={AlertTriangle}
          tone={instruments.atRisk > 0 ? "amber" : "muted"}
          value={instruments.atRisk.toString()}
          label={s.atRisk}
        />
        <Instrument
          icon={Sparkles}
          tone="emerald"
          value={`₪${(instruments.inRecovery / 1000).toFixed(0)}k`}
          label={s.inRecovery}
        />

        <div className="flex-1" />

        {/* Cmd-K affordance */}
        <button
          type="button"
          onClick={onOpenPalette}
          className="hidden md:inline-flex items-center gap-2 px-2.5 py-1 rounded-md text-[10.5px] text-white/40 hover:text-white/70 bg-white/[0.02] border border-white/[0.05] hover:border-white/[0.10] transition-colors"
        >
          <Search className="w-3 h-3" />
          <span>{s.palettePlaceholder.split("…")[0]}</span>
          <kbd className="font-mono text-[9.5px] text-white/35">⌘K</kbd>
        </button>

        {/* Lang toggle */}
        <div className="flex items-center gap-0.5 bg-surface-2 border border-border rounded-md p-0.5">
          {(["en", "he"] as const).map((l) => (
            <button
              key={l}
              type="button"
              onClick={() => setLang(l)}
              className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
                lang === l
                  ? "bg-gradient-to-br from-brand-500 to-indigo-500 text-white"
                  : "text-white/40 hover:text-white/80"
              }`}
              aria-pressed={lang === l}
            >
              {l === "he" ? "עב" : "EN"}
            </button>
          ))}
        </div>

        <span className="text-white/10">│</span>

        {/* On Watch — persistent brand pillar */}
        <OnWatchBadge s={s} ok={instruments.systemsOk} />
      </div>
    </div>
  );
}

function Instrument({
  icon: Icon,
  tone,
  value,
  label,
}: {
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
  tone: "violet" | "amber" | "emerald" | "muted";
  value: string;
  label: string;
}) {
  const ink =
    tone === "violet" ? "#a78bfa"
    : tone === "amber"   ? "#fbbf24"
    : tone === "emerald" ? "#34d399"
    : "rgba(255,255,255,0.30)";
  return (
    <span className="inline-flex items-center gap-1.5">
      <Icon className="w-3 h-3" style={{ color: ink }} />
      <span className="tabular-nums text-white/85" style={{ color: ink }}>{value}</span>
      <span className="text-white/40">{label}</span>
    </span>
  );
}

function OnWatchBadge({ s, ok }: { s: HomeStrings; ok: boolean }) {
  return (
    <span className="inline-flex items-center gap-2 text-[10.5px]">
      <MayaOrb size={14} state="idle" />
      <span className="tracking-[0.18em] text-white/70 uppercase">{s.onWatch}</span>
      <span
        className="w-1 h-1 rounded-full"
        style={{
          background: ok ? "#10b981" : "#fb7185",
          boxShadow: `0 0 6px ${ok ? "#10b981" : "#fb7185"}`,
        }}
      />
    </span>
  );
}

// ───────────────────────────────────────────────────────────────────
// Briefing panel — the ritual document
// ───────────────────────────────────────────────────────────────────
function BriefingPanel({
  data,
  s,
  orbState,
}: {
  data: MayaHomeData;
  s: HomeStrings;
  orbState: OrbState;
}) {
  const prepared = new Date(data.briefing.preparedAt);
  const updated = new Date(data.briefing.updatedAt);
  const fmtTime = (d: Date) =>
    d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });

  return (
    <section className="maya-fade">
      {/* Header chrome */}
      <div className="flex items-start gap-4">
        <MayaOrb size={36} state={orbState} />
        <div className="flex-1 min-w-0">
          <h1 className="text-[28px] md:text-[32px] font-semibold tracking-tight leading-[1.05] text-white">
            {greeting(data.ownerFirstName)}
          </h1>
          <p className="mt-1.5 text-[11px] font-mono tracking-wide text-white/35">
            {s.preparedAt(fmtTime(prepared))} · {s.updatedAt(fmtTime(updated))}
          </p>
        </div>
      </div>

      {/* HEADLINE */}
      <div className="mt-7">
        <SectionLabel>{s.sectionHeadline}</SectionLabel>
        <div className="mt-2 space-y-1.5">
          {data.briefing.headlineLines.map((line, i) => (
            <p
              key={i}
              className={`leading-snug tracking-tight ${
                i === 0
                  ? "text-[20px] md:text-[22px] font-medium text-white"
                  : "text-[16px] md:text-[17px] font-normal text-white/75"
              }`}
            >
              {line}
            </p>
          ))}
        </div>
      </div>

      {/* OVERNIGHT */}
      <BriefingList
        title={s.sectionOvernight}
        items={data.briefing.overnight}
      />

      {/* LOOK AHEAD */}
      <BriefingList
        title={s.sectionLookAhead}
        items={data.briefing.lookAhead}
      />
    </section>
  );
}

function BriefingList({
  title,
  items,
}: {
  title: string;
  items: { text: string; emphasis?: "fact" | "estimate" | "note"; yesterdayCallback?: boolean }[];
}) {
  return (
    <div className="mt-7">
      <SectionLabel>{title}</SectionLabel>
      <ul className="mt-2 space-y-2">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-3 text-[15px] leading-relaxed">
            <span
              className="mt-2.5 w-1 h-1 rounded-full flex-shrink-0"
              style={{
                background: item.yesterdayCallback ? "rgba(167,139,250,0.65)" : "rgba(255,255,255,0.22)",
              }}
            />
            <span
              className={
                item.emphasis === "estimate"
                  ? "italic text-white/55"
                  : item.yesterdayCallback
                  ? "text-white/65 italic"
                  : "text-white/82"
              }
            >
              {item.text}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-mono tracking-[0.24em] uppercase text-brand-300/70">
      {children}
    </p>
  );
}

function greeting(firstName: string): string {
  const h = new Date().getHours();
  // Plain English / Hebrew morning/afternoon/evening — pulled from time, not lang
  if (h < 12) return `Good morning, ${firstName}.`;
  if (h < 18) return `Good afternoon, ${firstName}.`;
  return `Good evening, ${firstName}.`;
}

// ───────────────────────────────────────────────────────────────────
// Decisions column
// ───────────────────────────────────────────────────────────────────
function DecisionsColumn({
  decisions,
  s,
  resolvedCount,
  onApprove,
  onOverride,
}: {
  decisions: Decision[];
  s: HomeStrings;
  resolvedCount: number;
  onApprove: (id: string) => void;
  onOverride: (id: string) => void;
}) {
  return (
    <aside className="maya-fade" style={{ animationDelay: "120ms" }}>
      <div className="flex items-baseline justify-between mb-3">
        <SectionLabel>{s.decisionsHeader(decisions.length)}</SectionLabel>
        {resolvedCount > 0 && (
          <span className="text-[10px] font-mono text-emerald-300/70 tracking-wide">
            {resolvedCount} ✓
          </span>
        )}
      </div>

      {decisions.length === 0 ? (
        <div className="rounded-2xl border border-emerald-500/15 bg-emerald-500/[0.04] p-5 text-center">
          <CheckCircle2 className="w-4 h-4 text-emerald-400/70 mx-auto" />
          <p className="mt-2 text-[13px] text-white/55">{s.decisionsAllClear}</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {decisions.map((d, i) => (
            <DecisionCard
              key={d.id}
              decision={d}
              s={s}
              onApprove={() => onApprove(d.id)}
              onOverride={() => onOverride(d.id)}
              delayMs={i * 80}
            />
          ))}
        </ul>
      )}
    </aside>
  );
}

function DecisionCard({
  decision,
  s,
  onApprove,
  onOverride,
  delayMs,
}: {
  decision: Decision;
  s: HomeStrings;
  onApprove: () => void;
  onOverride: () => void;
  delayMs: number;
}) {
  const isWatching = decision.tone === "watching";
  const accent = isWatching ? "#a78bfa" : "#34d399";

  return (
    <li
      className="relative rounded-2xl border border-white/[0.06] bg-surface-1/70 p-4 maya-fade"
      style={{ animationDelay: `${delayMs}ms` }}
    >
      {/* tone bar */}
      <span
        className="absolute top-4 bottom-4 start-0 w-[2px] rounded-full"
        style={{ background: accent, boxShadow: `0 0 10px ${accent}55` }}
      />

      <div className="ps-3">
        {/* header row */}
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-[14px] font-semibold text-white tracking-tight truncate">
            {decision.who}
          </p>
          {decision.channel && (
            <span className="text-[10px] font-mono text-white/35 truncate flex-shrink-0">
              {decision.channel}
            </span>
          )}
        </div>

        {/* context */}
        <p className="mt-2 text-[12.5px] text-white/55 leading-snug">{decision.context}</p>

        {/* recommendation */}
        <div className="mt-3">
          <p className="text-[9.5px] font-mono tracking-[0.20em] uppercase text-white/35">
            {isWatching ? s.decisionWatching : s.decisionRecommendLabel}
          </p>
          <p className="mt-1 text-[13.5px] text-white/90 leading-snug">
            {decision.recommendation}
          </p>
          {decision.rationale && (
            <p className="mt-1.5 text-[11.5px] text-white/45 italic leading-snug">
              {decision.rationale}
            </p>
          )}
        </div>

        {/* footer row: estimate + actions */}
        <div className="mt-4 flex items-center justify-between gap-2">
          {decision.recoveredEstimate ? (
            <span className="text-[10.5px] font-mono text-emerald-300/75">
              {s.decisionRecovers(`₪${decision.recoveredEstimate.toLocaleString("en-US")}`)}
            </span>
          ) : (
            <span />
          )}
          {!isWatching && (
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={onOverride}
                className="text-[11.5px] font-medium px-2.5 py-1 rounded-md text-white/55 hover:text-white hover:bg-white/[0.04] transition-colors"
              >
                {s.decisionOverride}
              </button>
              <button
                type="button"
                onClick={onApprove}
                className="text-[11.5px] font-semibold px-3 py-1.5 rounded-md bg-gradient-to-br from-emerald-500/85 to-emerald-600/85 text-white hover:from-emerald-400 hover:to-emerald-500 transition-all shadow-[0_0_16px_rgba(16,185,129,0.18)]"
              >
                {s.decisionApprove}
              </button>
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

// ───────────────────────────────────────────────────────────────────
// Active Missions Row
// ───────────────────────────────────────────────────────────────────
function ActiveMissionsRow({
  missions,
  s,
  dir,
}: {
  missions: Mission[];
  s: HomeStrings;
  dir: "rtl" | "ltr";
}) {
  return (
    <section className="mt-10 maya-fade" style={{ animationDelay: "240ms" }}>
      <div className="flex items-baseline justify-between mb-3">
        <SectionLabel>{s.missionsHeader}</SectionLabel>
      </div>
      <div className="rounded-2xl border border-white/[0.06] bg-surface-1/60 divide-y divide-white/[0.04]">
        {missions.map((m) => (
          <MissionRow key={m.id} mission={m} s={s} dir={dir} />
        ))}
      </div>
    </section>
  );
}

function MissionRow({
  mission,
  s,
  dir,
}: {
  mission: Mission;
  s: HomeStrings;
  dir: "rtl" | "ltr";
}) {
  return (
    <button
      type="button"
      className="group w-full flex items-center gap-5 px-5 py-4 hover:bg-white/[0.02] transition-colors text-start"
    >
      <div className="flex-1 min-w-0">
        <p className="text-[14px] font-semibold text-white tracking-tight">{mission.name}</p>
        <p className="mt-0.5 text-[11.5px] font-mono text-white/40 tabular-nums">
          {s.missionWeek(mission.weekCurrent, mission.weekTotal)} · {mission.capturedLabel}
        </p>
      </div>
      <Sparkline values={mission.spark} dir={dir} />
      <ChevronRight
        className={`w-4 h-4 text-white/25 group-hover:text-white/60 transition-colors ${
          dir === "rtl" ? "rotate-180" : ""
        }`}
      />
    </button>
  );
}

function Sparkline({ values, dir }: { values: number[]; dir: "rtl" | "ltr" }) {
  // Horizontal sparkline with subtle gradient under the curve.
  const w = 140;
  const h = 32;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * w;
    const y = h - ((v - min) / range) * (h - 4) - 2;
    return [x, y] as const;
  });
  const path = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const fill = `${path} L${w},${h} L0,${h} Z`;

  return (
    <svg
      width={w}
      height={h}
      className="flex-shrink-0"
      style={{ transform: dir === "rtl" ? "scaleX(-1)" : undefined }}
    >
      <defs>
        <linearGradient id="spark-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(167,139,250,0.30)" />
          <stop offset="100%" stopColor="rgba(167,139,250,0)" />
        </linearGradient>
      </defs>
      <path d={fill} fill="url(#spark-grad)" />
      <path d={path} fill="none" stroke="rgba(167,139,250,0.85)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      {/* End dot */}
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="2" fill="#a78bfa" />
    </svg>
  );
}

// ───────────────────────────────────────────────────────────────────
// Footer chrome (small, restrained)
// ───────────────────────────────────────────────────────────────────
function FooterChrome({ s }: { s: HomeStrings }) {
  return (
    <p className="mt-12 text-center text-[10px] tracking-[0.28em] text-white/15 uppercase font-mono">
      Maya · operating layer
    </p>
  );
}

// ───────────────────────────────────────────────────────────────────
// Night Watch surface — Maya On Watch as visible identity
// ───────────────────────────────────────────────────────────────────
function NightSurface({ s, orbState }: { s: HomeStrings; orbState: OrbState }) {
  return (
    <div className="absolute inset-0 z-[1] flex flex-col items-center justify-center px-6 maya-fade">
      <div className="flex flex-col items-center text-center max-w-md">
        <MayaOrb size={88} state={orbState} dim />

        <p className="mt-7 text-[10px] font-mono tracking-[0.32em] text-white/35 uppercase">
          {s.onWatch}
        </p>

        <h2 className="mt-3 text-[26px] md:text-[30px] font-semibold tracking-tight text-white/90 leading-snug">
          {s.nightWatchTitle}
        </h2>

        <p className="mt-5 text-[14px] text-white/55 font-mono">
          {s.nightWatchSub(4, 2)}
        </p>
        <p className="mt-2 text-[14px] text-white/65">
          {s.nightWatchPolicy}
        </p>

        <button
          type="button"
          className="mt-9 inline-flex items-center gap-2 text-[12px] font-medium px-4 py-2 rounded-md text-white/65 hover:text-white border border-white/10 hover:border-white/25 transition-colors"
        >
          {s.nightWatchTakeOver}
          <ArrowUpRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// Demo controls (corner) — day/night toggle
// ───────────────────────────────────────────────────────────────────
function DemoToggle({
  s,
  mode,
  setMode,
}: {
  s: HomeStrings;
  mode: Mode;
  setMode: (m: Mode) => void;
}) {
  return (
    <div className="fixed bottom-4 end-4 z-[3] flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-surface-2/70 backdrop-blur-sm border border-white/[0.06]">
      <span className="text-[9px] font-mono tracking-[0.20em] uppercase text-white/35">
        {s.demoLabel}
      </span>
      {(["day", "night"] as const).map((m) => (
        <button
          key={m}
          type="button"
          onClick={() => setMode(m)}
          className={`text-[10.5px] font-medium px-2 py-0.5 rounded transition-colors ${
            mode === m
              ? "bg-white/[0.08] text-white"
              : "text-white/40 hover:text-white/70"
          }`}
          aria-pressed={mode === m}
        >
          {m === "day" ? s.demoModeDay : s.demoModeNight}
        </button>
      ))}
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// Command Palette (Cmd-K)
// ───────────────────────────────────────────────────────────────────
function CommandPalette({
  s,
  items,
  onClose,
}: {
  s: HomeStrings;
  items: PaletteItem[];
  onClose: () => void;
}) {
  const [q, setQ] = useState("");
  const [highlight, setHighlight] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return items;
    return items.filter(
      (it) =>
        it.title.toLowerCase().includes(t) ||
        (it.subtitle ?? "").toLowerCase().includes(t)
    );
  }, [q, items]);

  const grouped = useMemo(() => {
    const groups: Record<string, PaletteItem[]> = {};
    filtered.forEach((it) => {
      groups[it.group] = groups[it.group] || [];
      groups[it.group].push(it);
    });
    return groups;
  }, [filtered]);

  const groupOrder: PaletteItem["group"][] = ["lead", "mission", "briefing", "action"];
  const groupLabel: Record<PaletteItem["group"], string> = {
    lead: s.paletteGroupLead,
    mission: s.paletteGroupMission,
    briefing: s.paletteGroupBriefing,
    action: s.paletteGroupAction,
  };

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      onClose();
    }
  }

  return (
    <div
      className="fixed inset-0 z-[10] flex items-start justify-center pt-[14vh] px-4 maya-palette-fade"
      onClick={onClose}
    >
      <div
        className="absolute inset-0 bg-black/55 backdrop-blur-sm"
        aria-hidden
      />
      <div
        className="relative w-full max-w-[640px] rounded-2xl border border-white/[0.08] bg-surface-1/95 shadow-[0_20px_80px_rgba(0,0,0,0.55)] overflow-hidden maya-palette-pop"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-white/[0.06]">
          <Search className="w-4 h-4 text-white/40" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setHighlight(0);
            }}
            onKeyDown={onKey}
            placeholder={s.palettePlaceholder}
            className="flex-1 bg-transparent text-[14px] text-white placeholder-white/35 outline-none"
          />
          <button
            type="button"
            onClick={onClose}
            className="text-white/30 hover:text-white/70 transition-colors"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Results */}
        <div className="max-h-[52vh] overflow-y-auto px-2 py-2">
          {filtered.length === 0 ? (
            <p className="px-4 py-8 text-center text-[13px] text-white/40">{s.paletteEmpty}</p>
          ) : (
            groupOrder.map((g) => {
              const list = grouped[g];
              if (!list?.length) return null;
              return (
                <div key={g} className="mt-1 mb-2">
                  <p className="px-3 pt-2 pb-1 text-[10px] font-mono tracking-[0.20em] uppercase text-white/35">
                    {groupLabel[g]}
                  </p>
                  <ul>
                    {list.map((it) => {
                      const idx = filtered.indexOf(it);
                      const active = idx === highlight;
                      return (
                        <li key={it.id}>
                          <button
                            type="button"
                            onMouseEnter={() => setHighlight(idx)}
                            onClick={onClose}
                            className={`w-full text-start flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
                              active ? "bg-white/[0.06]" : "hover:bg-white/[0.03]"
                            }`}
                          >
                            <PaletteIcon group={it.group} />
                            <div className="flex-1 min-w-0">
                              <p className="text-[13.5px] text-white truncate">{it.title}</p>
                              {it.subtitle && (
                                <p className="text-[11px] text-white/40 truncate">{it.subtitle}</p>
                              )}
                            </div>
                            {active && (
                              <CornerDownLeft className="w-3.5 h-3.5 text-white/35" />
                            )}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-2.5 border-t border-white/[0.05] text-[10px] font-mono text-white/30">
          <span className="inline-flex items-center gap-1.5">
            <Command className="w-3 h-3" /> palette
          </span>
          <span className="inline-flex items-center gap-3">
            <span>↑↓ navigate</span>
            <span>↵ open</span>
            <span>esc close</span>
          </span>
        </div>
      </div>
    </div>
  );
}

function PaletteIcon({ group }: { group: PaletteItem["group"] }) {
  const Icon =
    group === "lead" ? Eye
    : group === "mission" ? Activity
    : group === "briefing" ? Sparkles
    : ChevronRight;
  return (
    <span className="w-7 h-7 rounded-md bg-white/[0.04] flex items-center justify-center flex-shrink-0">
      <Icon className="w-3.5 h-3.5 text-white/55" />
    </span>
  );
}

// ───────────────────────────────────────────────────────────────────
// Surface texture — subtle background. Different per mode.
// ───────────────────────────────────────────────────────────────────
function SurfaceTexture({ mode }: { mode: Mode }) {
  return (
    <>
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 z-0"
        style={{
          background: mode === "day"
            ? "radial-gradient(ellipse 80% 50% at 50% 0%, rgba(139,92,246,0.06) 0%, transparent 55%)"
            : "radial-gradient(ellipse 60% 50% at 50% 50%, rgba(76,29,149,0.10) 0%, transparent 60%)",
          transition: "opacity 700ms ease",
        }}
      />
    </>
  );
}

// ───────────────────────────────────────────────────────────────────
// Maya Orb — semantic state, never decorative
// ───────────────────────────────────────────────────────────────────
function MayaOrb({
  size = 36,
  state = "idle",
  dim = false,
}: {
  size?: number;
  state?: OrbState;
  dim?: boolean;
}) {
  // State maps to subtle visual differences. No theatrical motion.
  const auraClass =
    state === "working" ? "maya-orb-working"
    : state === "watching" ? "maya-orb-watching"
    : state === "heard" ? "maya-orb-heard"
    : "maya-orb-idle";

  return (
    <div
      className="relative flex-shrink-0"
      style={{ width: size, height: size, opacity: dim ? 0.85 : 1 }}
      aria-hidden
    >
      <span
        className={`absolute inset-0 rounded-full ${auraClass}`}
        style={{
          background:
            "radial-gradient(circle, rgba(139,92,246,0.32) 0%, rgba(139,92,246,0) 65%)",
        }}
      />
      <span
        className="absolute inset-[18%] rounded-full"
        style={{
          background:
            "radial-gradient(circle at 35% 30%, rgba(255,255,255,0.95) 0%, #c4b5fd 22%, #8b5cf6 60%, #4c1d95 100%)",
          boxShadow:
            "0 0 18px rgba(139,92,246,0.45), inset 0 0 10px rgba(255,255,255,0.22)",
        }}
      />
      <span
        className="absolute rounded-full pointer-events-none"
        style={{
          width: size * 0.18,
          height: size * 0.18,
          left: size * 0.32,
          top: size * 0.26,
          background: "radial-gradient(circle, rgba(255,255,255,0.85) 0%, transparent 70%)",
          filter: "blur(1px)",
        }}
      />
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// Surface CSS — keyframes, hebrew typography, mode shifts
// ───────────────────────────────────────────────────────────────────
const SURFACE_CSS = `
  .maya-hebrew {
    font-family: "Heebo", "Assistant", "Rubik", "Segoe UI", "Helvetica Neue", system-ui, sans-serif;
  }

  .maya-night {
    /* night dim — lower contrast, calm, slightly cooler */
    color-scheme: dark;
  }
  .maya-night .maya-fade {
    opacity: 0.85;
  }

  /* Surface fade-in — calm, no theater */
  .maya-fade {
    opacity: 0;
    animation: maya-fade-in 520ms cubic-bezier(0.16,1,0.3,1) forwards;
  }
  @keyframes maya-fade-in {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: translateY(0);   }
  }

  /* Orb states — subtle, semantic */
  .maya-orb-idle    { animation: maya-orb-idle 3.6s ease-in-out infinite; }
  .maya-orb-working { animation: maya-orb-working 1.8s ease-in-out infinite; }
  .maya-orb-watching{ animation: maya-orb-watching 5.0s ease-in-out infinite; opacity: 0.7; }
  .maya-orb-heard   { animation: maya-orb-heard 0.5s ease-out 1; }

  @keyframes maya-orb-idle {
    0%, 100% { transform: scale(1);    opacity: 0.85; }
    50%      { transform: scale(1.10); opacity: 1.00; }
  }
  @keyframes maya-orb-working {
    0%, 100% { transform: scale(1.04); opacity: 0.95; }
    50%      { transform: scale(1.18); opacity: 1.00; }
  }
  @keyframes maya-orb-watching {
    0%, 100% { transform: scale(1);    opacity: 0.65; }
    50%      { transform: scale(1.04); opacity: 0.78; }
  }
  @keyframes maya-orb-heard {
    0%   { transform: scale(1);    opacity: 0.85; }
    50%  { transform: scale(1.30); opacity: 1.00; }
    100% { transform: scale(1);    opacity: 0.85; }
  }

  /* Command palette */
  .maya-palette-fade {
    animation: maya-palette-fade 180ms ease-out;
  }
  .maya-palette-pop {
    animation: maya-palette-pop 200ms cubic-bezier(0.16,1,0.3,1);
    transform-origin: top center;
  }
  @keyframes maya-palette-fade {
    from { opacity: 0; }
    to   { opacity: 1; }
  }
  @keyframes maya-palette-pop {
    from { opacity: 0; transform: translateY(-8px) scale(0.98); }
    to   { opacity: 1; transform: translateY(0)    scale(1);    }
  }

  @media (prefers-reduced-motion: reduce) {
    .maya-fade,
    .maya-orb-idle, .maya-orb-working, .maya-orb-watching, .maya-orb-heard,
    .maya-palette-fade, .maya-palette-pop {
      animation: none !important;
      transition: none !important;
      opacity: 1 !important;
      transform: none !important;
    }
  }
`;

function SurfaceCss() {
  return <style dangerouslySetInnerHTML={{ __html: SURFACE_CSS }} />;
}
