"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CircleDot,
  Mic,
  Radio,
  ShieldAlert,
  Sparkles,
  Stethoscope,
  Target,
  TrendingUp,
} from "lucide-react";
import { useLanguage } from "@/context/language-context";
import type {
  MriDiagnosticSignal,
  MriDimension,
  MriLeak,
  MriMockData,
  Severity,
} from "./mri-mock-data";
import { MRI_STRINGS, type MriLang, type MriStrings } from "./mri-strings";

// ───────────────────────────────────────────────────────────────────
// Reveal sequence configuration
// ───────────────────────────────────────────────────────────────────
const STEP_DELAY_MS = 1700;           // time each scan step is "active"
const TYPEWRITER_MS = 38;             // per-character speed
const HOLD_BEFORE_VERDICT_MS = 500;   // pause after last scan step

// ───────────────────────────────────────────────────────────────────
// Severity styling — temperature scale, used in multiple places
// ───────────────────────────────────────────────────────────────────
const SEVERITY_THEME: Record<
  Severity,
  { ink: string; bg: string; ring: string; accent: string }
> = {
  low:      { ink: "#34d399", bg: "rgba(16,185,129,0.10)", ring: "rgba(16,185,129,0.30)", accent: "#10b981" },
  moderate: { ink: "#a78bfa", bg: "rgba(139,92,246,0.10)", ring: "rgba(139,92,246,0.28)", accent: "#8b5cf6" },
  high:     { ink: "#fbbf24", bg: "rgba(245,158,11,0.10)", ring: "rgba(245,158,11,0.30)", accent: "#f59e0b" },
  critical: { ink: "#fb7185", bg: "rgba(244,63,94,0.10)",  ring: "rgba(244,63,94,0.32)",  accent: "#f43f5e" },
};

const SIGNAL_STATE_COLOR: Record<MriDiagnosticSignal["state"], { dot: string; ring: string }> = {
  ok:    { dot: "#10b981", ring: "rgba(16,185,129,0.32)" },
  watch: { dot: "#fbbf24", ring: "rgba(245,158,11,0.32)" },
  alert: { dot: "#fb7185", ring: "rgba(244,63,94,0.34)"  },
};

function severityValue(sev: Severity, s: MriStrings): string {
  switch (sev) {
    case "critical": return s.heroSeverityValueCritical;
    case "high":     return s.heroSeverityValueHigh;
    case "moderate": return s.heroSeverityValueModerate;
    case "low":      return s.heroSeverityValueLow;
  }
}

function formatMoney(n: number): string {
  // Currency symbol comes from data; we always group with comma per Israeli convention.
  return n.toLocaleString("en-US");
}

// hex → rgba helper
function hexA(hex: string, a: number) {
  const h = hex.replace("#", "");
  const r = parseInt(h.length === 3 ? h[0] + h[0] : h.slice(0, 2), 16);
  const g = parseInt(h.length === 3 ? h[1] + h[1] : h.slice(2, 4), 16);
  const b = parseInt(h.length === 3 ? h[2] + h[2] : h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
}

// ───────────────────────────────────────────────────────────────────
// Top-level
// ───────────────────────────────────────────────────────────────────
type Stage = "scan" | "verdict" | "main";

export function MriCommandCenter({ data }: { data: MriMockData }) {
  const { lang } = useLanguage();
  const mriLang: MriLang = lang === "he" ? "he" : "en";
  const s = MRI_STRINGS[mriLang];
  const dir: "rtl" | "ltr" = mriLang === "he" ? "rtl" : "ltr";

  const [stage, setStage] = useState<Stage>("scan");

  // Skip-on-keypress: lets demo presenters jump straight to main
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === " " || e.key === "Enter" || e.key === "Escape") {
        if (stage !== "main") {
          e.preventDefault();
          setStage("main");
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stage]);

  return (
    <div
      dir={dir}
      lang={mriLang}
      className={`relative flex-1 overflow-y-auto overflow-x-hidden bg-surface-0 text-white ${
        mriLang === "he" ? "mri-hebrew" : ""
      }`}
    >
      <ScanGrid intensity={stage === "main" ? 0.32 : 1} />
      <MWatermark />

      {stage === "scan" && (
        <ScanReveal s={s} onDone={() => setStage("verdict")} />
      )}
      {stage === "verdict" && (
        <VerdictMoment data={data} s={s} onDone={() => setStage("main")} />
      )}

      {stage === "main" && (
        <div className="relative z-[1] max-w-[1320px] mx-auto px-6 md:px-10 py-8 md:py-10">
          <DocumentChrome data={data} s={s} />
          <HeroMetrics data={data} s={s} />
          <PrimaryLeakBanner data={data} s={s} />
          <LeakMap leaks={data.topLeaks} severity={data.severity} s={s} dir={dir} />
          <RecoveryProjection data={data} s={s} />
          <DiagnosticCoverage signals={data.signals} summary={data.signalSummary} s={s} />
          <EvidenceWall evidence={data.evidence} s={s} />
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 mt-8">
            <ExecutiveBrief s={s} className="lg:col-span-3" />
            <RecommendedPriority s={s} className="lg:col-span-2" />
          </div>
          <TalkToMayaSection s={s} />
          <Footer s={s} />
        </div>
      )}

      <CinematicCss />
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// 1) Scan reveal sequence
// ───────────────────────────────────────────────────────────────────
function ScanReveal({ s, onDone }: { s: MriStrings; onDone: () => void }) {
  const [stepIndex, setStepIndex] = useState(0);
  const [typed, setTyped] = useState("");
  const steps = s.revealSteps;
  const currentStep = steps[stepIndex];

  useEffect(() => {
    setTyped("");
    let i = 0;
    const id = window.setInterval(() => {
      i += 1;
      setTyped(currentStep.slice(0, i));
      if (i >= currentStep.length) window.clearInterval(id);
    }, TYPEWRITER_MS);
    return () => window.clearInterval(id);
  }, [currentStep]);

  useEffect(() => {
    const t = window.setTimeout(() => {
      if (stepIndex < steps.length - 1) {
        setStepIndex((i) => i + 1);
      } else {
        window.setTimeout(onDone, HOLD_BEFORE_VERDICT_MS);
      }
    }, STEP_DELAY_MS);
    return () => window.clearTimeout(t);
  }, [stepIndex, steps.length, onDone]);

  return (
    <div className="absolute inset-0 z-10 flex items-center justify-center px-6">
      <div className="flex flex-col items-center text-center max-w-md">
        <MayaOrb size={140} live />
        <p className="mt-6 text-[10px] tracking-[0.32em] text-brand-300/80 font-mono uppercase">
          {s.revealEyebrow}
        </p>

        <div className="mt-3 h-6">
          <p className="text-[15px] text-white/85 font-medium">
            {typed}
            <span className="inline-block w-[1ch] -ml-[1px] text-brand-400 animate-pulse">
              ▍
            </span>
          </p>
        </div>

        <ul className="mt-6 space-y-1.5 text-start w-72">
          {steps.map((step, i) => {
            const done = i < stepIndex;
            const active = i === stepIndex;
            return (
              <li
                key={step}
                className="flex items-center gap-2.5 text-[11px] font-mono"
                style={{
                  color: done
                    ? "rgba(167,139,250,0.85)"
                    : active
                    ? "#fff"
                    : "rgba(255,255,255,0.22)",
                }}
              >
                <span
                  className="w-1 h-1 rounded-full flex-shrink-0"
                  style={{
                    background: done ? "#a78bfa" : active ? "#fff" : "rgba(255,255,255,0.18)",
                    boxShadow: active ? "0 0 8px rgba(255,255,255,0.7)" : "none",
                  }}
                />
                <span className="truncate">{step}</span>
              </li>
            );
          })}
        </ul>

        <p className="mt-8 text-[9px] tracking-[0.2em] text-white/20 uppercase font-mono">
          {s.verdictTapHint}
        </p>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// 2) Verdict Moment — Money Leak MRI Scan (5 stages, ≤5s, skippable)
//    A. Revenue flow detected (₪152,050)
//    B. Three leak lines emerge sequentially
//    C. Diagnostic finding — number tints to rose ("escaping")
//    D. Opportunity reveal — number swaps to recoverable in violet
//    E. Orb scans throughout (medical-imaging sweep line)
// ───────────────────────────────────────────────────────────────────
type ScanStage = "flow" | "leak" | "escaping" | "recoverable";

function VerdictMoment({
  data,
  s,
  onDone,
}: {
  data: MriMockData;
  s: MriStrings;
  onDone: () => void;
}) {
  const totalLeak = useMemo(
    () => data.topLeaks.reduce((sum, l) => sum + l.amount, 0),
    [data.topLeaks]
  );
  const top3Leaks = useMemo(
    () =>
      [...data.topLeaks]
        .sort((a, b) => b.amount - a.amount)
        .slice(0, 3),
    [data.topLeaks]
  );

  const [stage, setStage] = useState<ScanStage>("flow");
  const [leakIdx, setLeakIdx] = useState<number>(-1);

  useEffect(() => {
    const timers: number[] = [];
    // Stage A held for 700ms (count-up to ₪152,050)
    timers.push(window.setTimeout(() => setStage("leak"), 700));
    // Stage B: three leak lines emerge sequentially
    timers.push(window.setTimeout(() => setLeakIdx(0), 850));
    timers.push(window.setTimeout(() => setLeakIdx(1), 1450));
    timers.push(window.setTimeout(() => setLeakIdx(2), 2050));
    // Stage C: number tints to rose, leaks fade out
    timers.push(window.setTimeout(() => setStage("escaping"), 2750));
    // Pause for drama, then Stage D: opportunity reveal
    timers.push(window.setTimeout(() => setStage("recoverable"), 3650));
    // Hold the recoverable, then transition to main
    timers.push(window.setTimeout(onDone, 5000));
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [onDone]);

  const eyebrow =
    stage === "flow"
      ? s.scanFlowEyebrow
      : stage === "leak"
      ? s.scanLeakEyebrow
      : stage === "escaping"
      ? s.scanEscapingEyebrow
      : s.scanRecoverableEyebrow;

  const numberTone =
    stage === "flow" || stage === "leak"
      ? "#ffffff"
      : stage === "escaping"
      ? "#fb7185"
      : "#a78bfa";

  return (
    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center px-6">
      {/* Top eyebrow — frame the experience */}
      <p className="text-[10px] tracking-[0.36em] text-brand-300/70 font-mono uppercase mri-stage-eyebrow">
        {s.verdictEyebrow}
      </p>

      {/* Maya orb with medical-scanner sweep line */}
      <div className="mt-6">
        <ScanOrb size={104} />
      </div>

      {/* Stage eyebrow (changes per stage with key-driven fade) */}
      <p
        key={`eb-${stage}`}
        className="mt-7 text-[11px] tracking-[0.30em] font-mono uppercase mri-stage-eyebrow"
        style={{ color: numberTone === "#ffffff" ? "rgba(255,255,255,0.55)" : numberTone }}
      >
        {eyebrow}
      </p>

      {/* Main number — counts on mount (A), holds static (B/C), swaps + counts in D */}
      <div className="mt-3 relative h-[88px] md:h-[104px] flex items-center justify-center">
        {stage === "flow" && (
          <p
            key="num-flow"
            className="text-[64px] md:text-[80px] font-semibold leading-none tracking-tight tabular-nums mri-num-fade"
            style={{
              color: numberTone,
              textShadow: `0 0 38px ${hexA(numberTone, 0.30)}`,
            }}
          >
            <span style={{ color: hexA(numberTone, 0.6) }}>{data.currency}</span>
            <CountUp to={totalLeak} duration={650} />
          </p>
        )}
        {(stage === "leak" || stage === "escaping") && (
          <p
            key={`num-static-${stage}`}
            className="text-[64px] md:text-[80px] font-semibold leading-none tracking-tight tabular-nums"
            style={{
              color: numberTone,
              textShadow: `0 0 38px ${hexA(numberTone, 0.30)}`,
              transition: "color 600ms ease, text-shadow 600ms ease",
            }}
          >
            <span style={{ color: hexA(numberTone, 0.6) }}>{data.currency}</span>
            {formatMoney(totalLeak)}
          </p>
        )}
        {stage === "recoverable" && (
          <p
            key="num-recoverable"
            className="text-[64px] md:text-[80px] font-semibold leading-none tracking-tight tabular-nums mri-num-swap-in"
            style={{
              color: numberTone,
              textShadow: `0 0 38px ${hexA(numberTone, 0.36)}`,
            }}
          >
            <span style={{ color: hexA(numberTone, 0.6) }}>{data.currency}</span>
            <CountUp to={data.recoverable} duration={950} />
          </p>
        )}
      </div>

      {/* Stage subtext zone */}
      <div className="mt-4 h-[80px] w-full max-w-md flex items-start justify-center">
        {stage === "flow" && (
          <p
            key="flow-sub"
            className="text-center text-[12px] text-white/45 font-mono mri-stage-eyebrow"
          >
            {s.scanFlowSub}
          </p>
        )}

        {stage === "leak" && (
          <ul className="flex flex-col items-center gap-1.5 w-full">
            {top3Leaks.map((leak, i) => (
              <LeakLine
                key={leak.key}
                visible={leakIdx >= i}
                label={s.scanLeakLineLabel(leak.label)}
                amount={leak.amount}
                currency={data.currency}
              />
            ))}
          </ul>
        )}

        {(stage === "escaping" || stage === "recoverable") && (
          <p
            key={`trail-${stage}`}
            className="text-center text-[11px] font-mono mri-stage-eyebrow"
            style={{ color: hexA(numberTone, 0.5) }}
          >
            {s.perMonth}
          </p>
        )}
      </div>

      <p className="mt-8 text-[9px] tracking-[0.2em] text-white/20 uppercase font-mono">
        {s.verdictTapHint}
      </p>
    </div>
  );
}

function LeakLine({
  visible,
  label,
  amount,
  currency,
}: {
  visible: boolean;
  label: string;
  amount: number;
  currency: string;
}) {
  return (
    <li
      className={`flex items-center gap-3 text-[13px] font-mono transition-all duration-500 ease-out ${
        visible ? "opacity-100 translate-y-0 blur-0" : "opacity-0 -translate-y-1 blur-sm"
      }`}
    >
      <span
        className="w-1 h-1 rounded-full flex-shrink-0"
        style={{ background: "#fb7185", boxShadow: "0 0 8px rgba(244,63,94,0.55)" }}
      />
      <span className="text-white/65">{label}</span>
      <span className="text-rose-400 tabular-nums font-semibold tracking-tight">
        −{currency}
        {formatMoney(amount)}
      </span>
    </li>
  );
}

// Maya orb wrapped with a slow medical-imaging scan line. Used only during the verdict.
function ScanOrb({ size = 100 }: { size?: number }) {
  return (
    <div
      className="relative flex-shrink-0"
      style={{ width: size, height: size }}
      aria-hidden
    >
      {/* breathing aura */}
      <span
        className="absolute inset-0 rounded-full mri-orb-breath"
        style={{
          background:
            "radial-gradient(circle, rgba(139,92,246,0.40) 0%, rgba(139,92,246,0) 65%)",
        }}
      />
      {/* core */}
      <span
        className="absolute inset-[18%] rounded-full overflow-hidden"
        style={{
          background:
            "radial-gradient(circle at 35% 30%, rgba(255,255,255,0.95) 0%, #c4b5fd 22%, #8b5cf6 60%, #4c1d95 100%)",
          boxShadow:
            "0 0 22px rgba(139,92,246,0.55), inset 0 0 12px rgba(255,255,255,0.25)",
        }}
      >
        {/* scanner sweep line */}
        <span className="absolute inset-x-[-15%] h-[2px] mri-scanner-line" />
      </span>
      {/* highlight */}
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
// Persistent scan grid
// ───────────────────────────────────────────────────────────────────
function ScanGrid({ intensity }: { intensity: number }) {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-0 mri-grid"
      style={{ opacity: intensity }}
    />
  );
}

// Tiny "M" watermark in the corner — quiet OS identity mark.
function MWatermark() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed bottom-6 end-6 z-0 select-none hidden md:block"
      style={{ opacity: 0.05 }}
    >
      <span className="text-[120px] font-black leading-none tracking-tighter text-white">
        M
      </span>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// Document chrome — clinical metadata strip + small persistent orb
// ───────────────────────────────────────────────────────────────────
function DocumentChrome({ data, s }: { data: MriMockData; s: MriStrings }) {
  const { lang, setLang } = useLanguage();
  const ts = new Date(data.scannedAt);
  const tsLabel =
    ts.toLocaleDateString("en-US", { month: "short", day: "2-digit" }) +
    " · " +
    ts.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });

  return (
    <div className="mri-stagger" style={{ animationDelay: "40ms" }}>
      <div className="flex items-center gap-3">
        <MayaOrb size={36} live />
        <div className="flex-1 min-w-0">
          <p className="text-[10px] tracking-[0.28em] text-brand-300/80 font-mono uppercase">
            {s.productPath}
          </p>
          <h1 className="mt-1 text-2xl md:text-3xl font-semibold text-white tracking-tight leading-none">
            {s.pageTitle}
          </h1>
        </div>
        <div className="hidden md:flex items-center gap-2.5">
          <div className="flex items-center gap-0.5 bg-surface-2 border border-border rounded-lg p-0.5">
            {(["en", "he"] as const).map((l) => (
              <button
                key={l}
                type="button"
                onClick={() => setLang(l)}
                className={`px-2 py-0.5 rounded-md text-[10px] font-medium tracking-wide transition-colors ${
                  lang === l
                    ? "bg-gradient-to-br from-brand-500 to-indigo-500 text-white shadow-glow-sm"
                    : "text-white/45 hover:text-white/85"
                }`}
                aria-pressed={lang === l}
              >
                {l === "he" ? "עב" : "EN"}
              </button>
            ))}
          </div>
          <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
            <span className="live-dot" />
            {s.liveChip}
          </span>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px] font-mono text-white/45">
        <span>
          {s.patient}&nbsp;
          <span className="text-white/85">{s.patientName}</span>
        </span>
        <span className="hidden md:inline text-white/15">│</span>
        <span>{s.patientVertical}</span>
        <span className="hidden md:inline text-white/15">│</span>
        <span>
          {s.scan}&nbsp;<span className="text-white/70">{data.scanId}</span>
        </span>
        <span className="hidden md:inline text-white/15">│</span>
        <span>{tsLabel}</span>
        <span className="hidden md:inline text-white/15">│</span>
        <span>
          {s.confidence}&nbsp;
          <span className="text-white/70">{Math.round(data.confidence * 100)}%</span>
        </span>
      </div>

      <div className="mt-6 h-px w-full bg-gradient-to-r from-transparent via-white/10 to-transparent" />
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// 3) Hero metrics — gauge + cinematic count-up + alert-grade severity
// ───────────────────────────────────────────────────────────────────
function HeroMetrics({ data, s }: { data: MriMockData; s: MriStrings }) {
  const sev = SEVERITY_THEME[data.severity];

  return (
    <div
      className="mt-7 grid grid-cols-1 md:grid-cols-3 gap-5 mri-stagger"
      style={{ animationDelay: "180ms" }}
    >
      <HeroCard label={s.heroScoreLabel} hint={s.heroScoreHint}>
        <div className="flex items-center gap-5">
          <ScoreGauge value={data.score} />
          <div className="min-w-0">
            <p className="text-[44px] font-semibold leading-none tracking-tight tabular-nums text-white">
              {data.score}
              <span className="text-white/30 text-[22px] ms-1 font-medium">/100</span>
            </p>
            <p className="text-[11px] mt-2 text-white/45">{s.heroScoreNote}</p>
          </div>
        </div>
      </HeroCard>

      <HeroCard label={s.heroRecoverableLabel} hint={s.heroRecoverableHint}>
        <div>
          <p className="relative text-[44px] font-semibold leading-none tracking-tight tabular-nums text-white inline-block">
            <CountUp to={data.recoverable} prefix={data.currency} duration={1500} />
            <span aria-hidden className="absolute inset-0 mri-cinema-sweep pointer-events-none" />
          </p>
          <p className="text-[11px] mt-3 text-white/45">{s.heroRecoverableNote}</p>
        </div>
      </HeroCard>

      <HeroCard
        label={s.heroSeverityLabel}
        hint={s.heroSeverityHint}
        alert={data.severity === "critical" || data.severity === "high"}
      >
        <div className="flex items-stretch gap-4">
          <div
            className="w-1.5 rounded-full flex-shrink-0 mri-sev-bar"
            style={{ background: sev.accent, boxShadow: `0 0 18px ${sev.ring}` }}
          />
          <div className="min-w-0">
            <span
              className="inline-flex items-center gap-1.5 text-[9px] font-mono tracking-[0.22em] px-1.5 py-0.5 rounded mri-alert-chip"
              style={{ color: sev.ink, background: sev.bg, boxShadow: `inset 0 0 0 1px ${sev.ring}` }}
            >
              <span className="mri-alert-dot" style={{ background: sev.ink, boxShadow: `0 0 6px ${sev.ink}` }} />
              {s.heroSeverityAlertChip}
            </span>
            <div className="mt-2 flex items-baseline gap-2">
              <p
                className="text-[36px] font-semibold leading-none tracking-tight"
                style={{ color: sev.ink, textShadow: `0 0 16px ${hexA(sev.accent, 0.35)}` }}
              >
                {severityValue(data.severity, s)}
              </p>
              <ShieldAlert className="w-4 h-4" style={{ color: sev.ink }} />
            </div>
            <p className="text-[11px] mt-3 text-white/45">{s.heroSeverityNote}</p>
          </div>
        </div>
      </HeroCard>
    </div>
  );
}

function HeroCard({
  label,
  hint,
  children,
  alert = false,
}: {
  label: string;
  hint: string;
  children: React.ReactNode;
  alert?: boolean;
}) {
  return (
    <div
      className={`relative rounded-2xl bg-surface-1 border border-border p-5 overflow-hidden ${
        alert ? "mri-alert-frame" : ""
      }`}
    >
      <div
        aria-hidden
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 80% 40% at 0% 0%, rgba(139,92,246,0.07) 0%, transparent 60%)",
        }}
      />
      <div className="relative">
        <div className="flex items-center justify-between mb-4 gap-2">
          <p className="text-[10px] tracking-[0.18em] text-white/45 uppercase font-mono">
            {label}
          </p>
          <p className="text-[10px] text-white/25 font-mono">{hint}</p>
        </div>
        {children}
      </div>
    </div>
  );
}

// Circular gauge — animates dashoffset from full → target on mount
function ScoreGauge({ value }: { value: number }) {
  const size = 96;
  const stroke = 6;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const target = c - (value / 100) * c;
  const tone =
    value >= 80 ? "#10b981" : value >= 60 ? "#a78bfa" : value >= 40 ? "#f59e0b" : "#fb7185";

  const [filled, setFilled] = useState(false);
  useEffect(() => {
    const id = window.setTimeout(() => setFilled(true), 60);
    return () => window.clearTimeout(id);
  }, []);

  return (
    <svg width={size} height={size} className="flex-shrink-0 -rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} fill="none" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        stroke={tone}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={filled ? target : c}
        fill="none"
        style={{
          filter: `drop-shadow(0 0 8px ${tone}55)`,
          transition: "stroke-dashoffset 1300ms cubic-bezier(0.16,1,0.3,1)",
        }}
      />
    </svg>
  );
}

// Count-up that runs from 0 to `to`. Resets cleanly if `to`/`duration` change.
function CountUp({
  to,
  prefix = "",
  duration = 1200,
}: {
  to: number;
  prefix?: string;
  duration?: number;
}) {
  const [n, setN] = useState(0);

  useEffect(() => {
    setN(0);
    let raf = 0;
    let start: number | null = null;
    const tick = (ts: number) => {
      if (start === null) start = ts;
      const t = Math.min(1, (ts - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setN(Math.round(to * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [to, duration]);

  return <>{prefix + formatMoney(n)}</>;
}

// ───────────────────────────────────────────────────────────────────
// 3.5) Primary Leak Identified — narrative banner above LeakMap
// ───────────────────────────────────────────────────────────────────
function PrimaryLeakBanner({ data, s }: { data: MriMockData; s: MriStrings }) {
  const total = data.topLeaks.reduce((sum, l) => sum + l.amount, 0);
  const primary = [...data.topLeaks].sort((a, b) => b.amount - a.amount)[0];
  if (!primary) return null;
  const share = Math.round((primary.amount / total) * 100);

  return (
    <section className="mt-8 mri-stagger" style={{ animationDelay: "260ms" }}>
      <div
        className="relative rounded-2xl overflow-hidden border"
        style={{
          background:
            "linear-gradient(120deg, rgba(244,63,94,0.12) 0%, rgba(244,63,94,0.04) 35%, rgba(15,15,32,0) 70%)",
          borderColor: "rgba(244,63,94,0.20)",
        }}
      >
        {/* scanning line */}
        <span aria-hidden className="absolute inset-0 mri-detect-scan pointer-events-none" />

        <div className="relative flex items-center gap-4 px-5 py-4">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
            style={{
              background: "rgba(244,63,94,0.15)",
              boxShadow: "0 0 18px rgba(244,63,94,0.25), inset 0 0 0 1px rgba(244,63,94,0.30)",
            }}
          >
            <Target className="w-4 h-4" style={{ color: "#fb7185" }} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-mono tracking-[0.28em] uppercase" style={{ color: "#fb7185" }}>
              {s.primaryLeakEyebrow}
            </p>
            <p className="mt-1 text-white text-[16px] font-semibold tracking-tight">
              {s.primaryLeakLabelTpl(primary.label, share)}
            </p>
          </div>
          <p className="hidden md:block text-[11px] text-white/45 max-w-xs text-end leading-snug">
            {s.primaryLeakSub}
          </p>
        </div>
      </div>
    </section>
  );
}

// ───────────────────────────────────────────────────────────────────
// 4) Leak map — animated horizontal heat bars
// ───────────────────────────────────────────────────────────────────
function LeakMap({
  leaks,
  severity,
  s,
  dir,
}: {
  leaks: MriLeak[];
  severity: Severity;
  s: MriStrings;
  dir: "rtl" | "ltr";
}) {
  const total = useMemo(() => leaks.reduce((sum, l) => sum + l.amount, 0), [leaks]);
  const max = useMemo(() => Math.max(...leaks.map((l) => l.amount)), [leaks]);
  const tone = SEVERITY_THEME[severity];

  const [grown, setGrown] = useState(false);
  useEffect(() => {
    const id = window.setTimeout(() => setGrown(true), 60);
    return () => window.clearTimeout(id);
  }, []);

  return (
    <section className="mt-4 mri-stagger" style={{ animationDelay: "340ms" }}>
      <SectionHeader
        eyebrow={s.leakEyebrow}
        title={s.leakTitle}
        meta={`${s.leakTotalPrefix} ₪${formatMoney(total)} ${s.leakPerMonth}`}
        icon={Activity}
      />

      <div className="rounded-2xl bg-surface-1 border border-border p-6 mt-4">
        <ul className="space-y-5">
          {leaks.map((leak, i) => {
            const share = leak.amount / max;
            const gradientDir = dir === "rtl" ? "270deg" : "90deg";
            const fill = `linear-gradient(${gradientDir}, ${hexA(tone.accent, 0.55)} 0%, ${hexA(tone.accent, 0.95)} 100%)`;
            const glow = hexA(tone.accent, 0.35);

            return (
              <li key={leak.key} className="flex items-center gap-4">
                <div className="w-32 flex-shrink-0">
                  <p className="text-white/85 text-[13px] font-medium">{leak.label}</p>
                  <p className="text-white/35 text-[10px] font-mono mt-0.5">
                    {Math.round((leak.amount / total) * 100)}% {s.leakShareSuffix}
                  </p>
                </div>

                <div className="flex-1 h-7 rounded-md bg-white/[0.03] border border-white/[0.05] overflow-hidden relative">
                  <div
                    className="h-full"
                    style={{
                      width: grown ? `${share * 100}%` : "0%",
                      background: fill,
                      boxShadow: grown ? `0 0 14px ${glow}` : "none",
                      transition: `width 900ms cubic-bezier(0.16,1,0.3,1) ${500 + i * 110}ms, box-shadow 900ms ease ${500 + i * 110}ms`,
                    }}
                  />
                </div>

                <div className="w-28 text-end flex-shrink-0">
                  <p className="tabular-nums text-white text-[14px] font-semibold">
                    ₪{formatMoney(leak.amount)}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

// ───────────────────────────────────────────────────────────────────
// 4.5) Recovery Projection — Current vs With Maya
// ───────────────────────────────────────────────────────────────────
function RecoveryProjection({ data, s }: { data: MriMockData; s: MriStrings }) {
  const totalLeak = useMemo(
    () => data.topLeaks.reduce((sum, l) => sum + l.amount, 0),
    [data.topLeaks]
  );
  // Conservative 90-day recovery = 40% of recoverable opportunity (mock)
  const recovered90d = Math.round(data.recoverable * 0.40);
  const upliftPct = Math.round((recovered90d / totalLeak) * 100);

  const [mode, setMode] = useState<"current" | "projected">("current");

  return (
    <section className="mt-10 mri-stagger" style={{ animationDelay: "440ms" }}>
      <SectionHeader
        eyebrow={s.recoveryEyebrow}
        title={s.recoveryTitle}
        meta={`+${upliftPct}% ${s.recoveryDelta}`}
        icon={TrendingUp}
      />

      <div className="rounded-2xl bg-surface-1 border border-border p-6 mt-4">
        <div className="flex flex-col md:flex-row md:items-center gap-6">
          {/* Toggle */}
          <div className="inline-flex p-0.5 rounded-lg bg-surface-2 border border-border self-start md:self-center flex-shrink-0">
            <ToggleBtn
              active={mode === "current"}
              onClick={() => setMode("current")}
            >
              {s.recoveryToggleCurrent}
            </ToggleBtn>
            <ToggleBtn
              active={mode === "projected"}
              onClick={() => setMode("projected")}
            >
              {s.recoveryToggleProjected}
            </ToggleBtn>
          </div>

          {/* Two values, crossfade */}
          <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-6 min-w-0">
            <ProjectionStat
              active={mode === "current"}
              label={s.recoveryCurrentLabel}
              sub={s.recoveryCurrentSub}
              value={`-${data.currency}${formatMoney(totalLeak)}`}
              tone="#fb7185"
            />
            <ProjectionStat
              active={mode === "projected"}
              label={s.recoveryProjectedLabel}
              sub={s.recoveryProjectedSub}
              value={`+${data.currency}${formatMoney(recovered90d)}`}
              tone="#34d399"
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function ToggleBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`text-[11px] font-medium px-3 py-1.5 rounded-md transition-all ${
        active
          ? "bg-gradient-to-br from-brand-500 to-indigo-500 text-white shadow-glow-sm"
          : "text-white/55 hover:text-white"
      }`}
    >
      {children}
    </button>
  );
}

function ProjectionStat({
  active,
  label,
  sub,
  value,
  tone,
}: {
  active: boolean;
  label: string;
  sub: string;
  value: string;
  tone: string;
}) {
  return (
    <div
      className={`transition-all duration-500 ${
        active ? "opacity-100" : "opacity-30"
      }`}
    >
      <p className="text-[10px] font-mono tracking-[0.18em] text-white/45 uppercase">{label}</p>
      <p
        className="mt-2 text-[28px] md:text-[34px] font-semibold leading-none tracking-tight tabular-nums"
        style={{
          color: tone,
          textShadow: active ? `0 0 22px ${hexA(tone, 0.30)}` : "none",
        }}
      >
        {value}
      </p>
      <p className="mt-2 text-[11px] text-white/40">{sub}</p>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// 5) Diagnostic Coverage — 8-signal matrix
// ───────────────────────────────────────────────────────────────────
function DiagnosticCoverage({
  signals,
  summary,
  s,
}: {
  signals: MriDiagnosticSignal[];
  summary: MriMockData["signalSummary"];
  s: MriStrings;
}) {
  const active = signals.filter((sig) => sig.status === "active");
  const passive = signals.filter((sig) => sig.status === "passive");

  return (
    <section className="mt-10 mri-stagger" style={{ animationDelay: "560ms" }}>
      <SectionHeader
        eyebrow={s.coverageEyebrow}
        title={s.coverageTitle}
        meta={s.coverageMeta}
        icon={Radio}
      />

      <div className="flex flex-wrap gap-2 mt-4">
        <Chip ink="#a78bfa" bg="rgba(139,92,246,0.10)" ring="rgba(139,92,246,0.22)">
          <Sparkles className="w-3 h-3" />
          {s.signalsAnalyzed(summary.total)}
        </Chip>
        <Chip ink="#fbbf24" bg="rgba(245,158,11,0.10)" ring="rgba(245,158,11,0.22)">
          <CircleDot className="w-3 h-3" />
          {s.criticalFindings(summary.findings)}
        </Chip>
        <Chip ink="#fb7185" bg="rgba(244,63,94,0.10)" ring="rgba(244,63,94,0.26)">
          <AlertTriangle className="w-3 h-3" />
          {s.criticalAlert(summary.criticalAlerts)}
        </Chip>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-5">
        <CoverageColumn
          title={s.activeColumnTitle}
          subtitle={s.activeColumnSub}
          signals={active}
          marker={s.activeMarker}
          markerInk="#34d399"
          markerBg="rgba(16,185,129,0.10)"
          labels={s.signalLabels}
        />
        <CoverageColumn
          title={s.passiveColumnTitle}
          subtitle={s.passiveColumnSub}
          signals={passive}
          marker={s.passiveMarker}
          markerInk="#a78bfa"
          markerBg="rgba(139,92,246,0.10)"
          labels={s.signalLabels}
        />
      </div>
    </section>
  );
}

function CoverageColumn({
  title,
  subtitle,
  signals,
  marker,
  markerInk,
  markerBg,
  labels,
}: {
  title: string;
  subtitle: string;
  signals: MriDiagnosticSignal[];
  marker: string;
  markerInk: string;
  markerBg: string;
  labels: Record<string, string>;
}) {
  return (
    <div className="rounded-2xl bg-surface-1 border border-border p-5">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <p className="text-white text-[13px] font-semibold">{title}</p>
          <p className="text-white/40 text-[11px] mt-0.5">{subtitle}</p>
        </div>
        <span
          className="text-[9px] font-mono tracking-[0.2em] px-2 py-0.5 rounded"
          style={{ color: markerInk, background: markerBg }}
        >
          {marker}
        </span>
      </div>

      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {signals.map((sig, i) => {
          const tone = SIGNAL_STATE_COLOR[sig.state];
          const display = labels[sig.key] ?? sig.label;
          return (
            <li
              key={sig.key}
              className="flex items-center gap-2.5 px-3 py-2.5 rounded-lg bg-white/[0.02] border border-white/[0.04] mri-signal-in"
              style={{ animationDelay: `${640 + i * 70}ms` }}
            >
              <span className="relative flex-shrink-0">
                <span
                  className="block w-2 h-2 rounded-full"
                  style={{ background: tone.dot, boxShadow: `0 0 6px ${tone.dot}` }}
                />
                {sig.state !== "ok" && (
                  <span
                    className="absolute inset-0 rounded-full mri-signal-pulse"
                    style={{ boxShadow: `0 0 0 0 ${tone.ring}` }}
                  />
                )}
              </span>
              <span className="text-white/80 text-[12px] truncate">{display}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Chip({
  children,
  ink,
  bg,
  ring,
}: {
  children: React.ReactNode;
  ink: string;
  bg: string;
  ring: string;
}) {
  return (
    <span
      className="inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-full"
      style={{ color: ink, background: bg, boxShadow: `inset 0 0 0 1px ${ring}` }}
    >
      {children}
    </span>
  );
}

// ───────────────────────────────────────────────────────────────────
// 6) Evidence Wall — clinical specimen + dimension rings
// ───────────────────────────────────────────────────────────────────
function EvidenceWall({
  evidence,
  s,
}: {
  evidence: MriMockData["evidence"];
  s: MriStrings;
}) {
  return (
    <section className="mt-10 mri-stagger" style={{ animationDelay: "680ms" }}>
      <SectionHeader
        eyebrow={s.evidenceEyebrow}
        title={s.evidenceTitle}
        meta={`${s.evidenceChannelLabel} · ${s.evidenceTimestamp}`}
        icon={Stethoscope}
      />

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5 mt-4">
        <div className="lg:col-span-3 rounded-2xl bg-surface-1 border border-border p-6 relative overflow-hidden">
          <div className="flex items-center justify-between text-[10px] font-mono text-white/35 tracking-[0.18em] uppercase">
            <span>{s.evidenceChannelLabel}</span>
            <span>{s.evidenceTimestamp}</span>
          </div>

          <blockquote className="mt-5 text-[24px] md:text-[28px] leading-snug text-white/95 font-medium relative">
            <span className="absolute -start-3 -top-2 text-brand-400/40 text-[44px] leading-none font-serif select-none">
              &ldquo;
            </span>
            <span className="ps-3">{s.evidenceQuote}</span>
          </blockquote>

          <div className="mt-6 pt-5 border-t border-white/[0.06]">
            <p className="text-[10px] font-mono tracking-[0.18em] text-white/35 uppercase">
              {s.evidenceInterpretationLabel}
            </p>
            <p className="mt-2 text-[14px] leading-relaxed text-white/70">
              {s.evidenceInterpretation}
            </p>
          </div>
        </div>

        <div className="lg:col-span-2 rounded-2xl bg-surface-1 border border-border p-6">
          <p className="text-[10px] font-mono tracking-[0.18em] text-white/35 uppercase">
            {s.dimensionsHeader}
          </p>
          <ul className="mt-5 space-y-5">
            {evidence.dimensions.map((d, i) => (
              <DimensionRow
                key={d.key}
                dim={d}
                label={s.dimensionLabels[d.key] ?? d.label}
                delayMs={760 + i * 130}
              />
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

function DimensionRow({
  dim,
  label,
  delayMs,
}: {
  dim: MriDimension;
  label: string;
  delayMs: number;
}) {
  const pct = dim.score / dim.max;
  const tone =
    pct >= 0.7 ? "#10b981" : pct >= 0.5 ? "#a78bfa" : pct >= 0.3 ? "#f59e0b" : "#fb7185";

  const size = 38;
  const stroke = 4;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const target = c - pct * c;

  const [filled, setFilled] = useState(false);
  useEffect(() => {
    const id = window.setTimeout(() => setFilled(true), 60);
    return () => window.clearTimeout(id);
  }, []);

  return (
    <li
      className="flex items-center gap-4 mri-stagger"
      style={{ animationDelay: `${delayMs}ms` }}
    >
      <svg width={size} height={size} className="-rotate-90 flex-shrink-0">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} fill="none" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={tone}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={filled ? target : c}
          fill="none"
          style={{
            filter: `drop-shadow(0 0 4px ${tone}55)`,
            transition: "stroke-dashoffset 900ms cubic-bezier(0.16,1,0.3,1)",
            transitionDelay: `${delayMs}ms`,
          }}
        />
      </svg>
      <div className="flex-1 min-w-0">
        <p className="text-white/85 text-[13px] font-medium truncate">{label}</p>
      </div>
      <p className="tabular-nums text-white text-[14px] font-semibold flex-shrink-0">
        {dim.score}
        <span className="text-white/30 text-[12px] ms-0.5 font-medium">/{dim.max}</span>
      </p>
    </li>
  );
}

// ───────────────────────────────────────────────────────────────────
// 7) Maya Briefing — concise operator briefing (replaces report paragraph)
// ───────────────────────────────────────────────────────────────────
function ExecutiveBrief({ s, className = "" }: { s: MriStrings; className?: string }) {
  return (
    <section className={`mri-stagger ${className}`} style={{ animationDelay: "880ms" }}>
      <div className="rounded-2xl bg-surface-1 border border-border p-6 h-full flex flex-col relative overflow-hidden">
        {/* subtle indicator stripe */}
        <span
          aria-hidden
          className="absolute top-6 bottom-6 start-0 w-[2px] rounded-full"
          style={{
            background: "linear-gradient(to bottom, rgba(167,139,250,0.6) 0%, rgba(167,139,250,0) 100%)",
          }}
        />
        <div className="flex items-center gap-2 mb-4 ps-3">
          <MayaOrb size={18} live />
          <p className="text-[10px] font-mono tracking-[0.22em] text-brand-300/80 uppercase">
            {s.briefingEyebrow}
          </p>
        </div>
        <ul className="ps-3 space-y-3">
          {s.briefingLines.map((line, i) => (
            <li
              key={i}
              className="flex items-start gap-3 mri-briefing-line"
              style={{ animationDelay: `${980 + i * 140}ms` }}
            >
              <span className="text-brand-400/60 text-[14px] leading-snug font-mono mt-0.5 flex-shrink-0">
                {String(i + 1).padStart(2, "0")}
              </span>
              <p className="text-[15px] leading-relaxed text-white/85">{line}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

// ───────────────────────────────────────────────────────────────────
// 8) Recommended Priority
// ───────────────────────────────────────────────────────────────────
function RecommendedPriority({
  s,
  className = "",
}: {
  s: MriStrings;
  className?: string;
}) {
  return (
    <section className={`mri-stagger ${className}`} style={{ animationDelay: "1000ms" }}>
      <div className="rounded-2xl bg-surface-1 border border-border p-6 h-full flex flex-col">
        <div className="flex items-center gap-2 mb-3">
          <ArrowRight className="w-3.5 h-3.5 text-brand-300" />
          <p className="text-[10px] font-mono tracking-[0.18em] text-brand-300/80 uppercase">
            {s.priorityEyebrow}
          </p>
        </div>
        <p className="text-[15px] leading-snug text-white font-medium">{s.priorityFocus}</p>
        <p className="mt-2 text-[12px] text-white/50">{s.priorityRationale}</p>

        <div className="flex-1" />

        <button
          type="button"
          disabled
          className="mt-5 inline-flex items-center justify-center gap-2 w-full text-[13px] font-semibold px-4 py-2.5 rounded-lg
            bg-gradient-to-br from-brand-500 to-indigo-500 text-white
            shadow-glow-sm hover:from-brand-400 hover:to-indigo-400 transition-all
            disabled:opacity-60 disabled:cursor-not-allowed"
          aria-disabled="true"
        >
          {s.priorityCta}
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </section>
  );
}

// ───────────────────────────────────────────────────────────────────
// 9) Talk to Maya — copilot/advisor layer
// ───────────────────────────────────────────────────────────────────
function TalkToMayaSection({ s }: { s: MriStrings }) {
  return (
    <section className="mt-8 mri-stagger" style={{ animationDelay: "1120ms" }}>
      <div className="relative rounded-2xl bg-surface-1 border border-border p-6 overflow-hidden">
        {/* faint copilot accent */}
        <div
          aria-hidden
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              "radial-gradient(ellipse 60% 80% at 0% 50%, rgba(139,92,246,0.10) 0%, transparent 60%)",
          }}
        />

        <div className="relative flex flex-col md:flex-row md:items-center gap-5">
          <div className="flex items-center gap-4 flex-shrink-0">
            <CopilotOrb size={56} />
            <div className="md:hidden">
              <p className="text-[10px] font-mono tracking-[0.22em] text-brand-300/80 uppercase">
                {s.copilotEyebrow}
              </p>
              <p className="text-white text-[14px] font-semibold mt-1">{s.copilotTitle}</p>
            </div>
          </div>

          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-mono tracking-[0.22em] text-brand-300/80 uppercase hidden md:block">
              {s.copilotEyebrow}
            </p>
            <p className="text-white text-[15px] font-semibold mt-1 hidden md:block">
              {s.copilotTitle}
            </p>

            {/* Maya Insight */}
            <div className="mt-3 flex items-start gap-2.5">
              <span className="text-brand-300/70 text-[10px] font-mono tracking-[0.2em] uppercase mt-1 flex-shrink-0">
                {s.copilotInsightLabel}
              </span>
              <p className="text-white/85 text-[14px] leading-relaxed">{s.copilotInsight}</p>
            </div>

            <p className="mt-3 inline-flex items-center gap-1.5 text-[10px] font-mono text-emerald-300/80">
              <span className="live-dot" />
              {s.copilotListening}
            </p>
          </div>

          <button
            type="button"
            className="inline-flex items-center justify-center gap-2 text-[12px] font-semibold px-4 py-2.5 rounded-lg
              bg-gradient-to-br from-brand-500/90 to-indigo-500/90 text-white
              hover:from-brand-400 hover:to-indigo-400 transition-all
              shadow-glow-sm flex-shrink-0"
            title={s.copilotCta}
          >
            <Mic className="w-3.5 h-3.5" />
            {s.copilotCta}
          </button>
        </div>
      </div>
    </section>
  );
}

// Copilot orb — orb + audio-wave-style listening rings emanating outward
function CopilotOrb({ size = 56 }: { size?: number }) {
  return (
    <div
      className="relative flex-shrink-0"
      style={{ width: size, height: size }}
      aria-hidden
    >
      {/* listening rings */}
      <span className="absolute inset-0 rounded-full mri-copilot-ring" style={{ animationDelay: "0s" }} />
      <span className="absolute inset-0 rounded-full mri-copilot-ring" style={{ animationDelay: "1s" }} />
      <span className="absolute inset-0 rounded-full mri-copilot-ring" style={{ animationDelay: "2s" }} />
      {/* core */}
      <span
        className="absolute inset-[16%] rounded-full mri-orb-breath"
        style={{
          background:
            "radial-gradient(circle at 35% 30%, rgba(255,255,255,0.95) 0%, #c4b5fd 22%, #8b5cf6 60%, #4c1d95 100%)",
          boxShadow:
            "0 0 22px rgba(139,92,246,0.55), inset 0 0 12px rgba(255,255,255,0.25)",
        }}
      />
    </div>
  );
}

function Footer({ s }: { s: MriStrings }) {
  return (
    <p className="mt-12 pb-2 text-center text-[10px] tracking-[0.28em] text-white/20 uppercase font-mono">
      {s.footer}
    </p>
  );
}

// ───────────────────────────────────────────────────────────────────
// Section header — shared chrome
// ───────────────────────────────────────────────────────────────────
function SectionHeader({
  eyebrow,
  title,
  meta,
  icon: Icon,
}: {
  eyebrow: string;
  title: string;
  meta?: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="flex items-end justify-between gap-4">
      <div>
        <div className="flex items-center gap-2">
          <Icon className="w-3.5 h-3.5 text-brand-300" />
          <p className="text-[10px] font-mono tracking-[0.22em] text-brand-300/80 uppercase">
            {eyebrow}
          </p>
        </div>
        <h2 className="mt-1.5 text-white text-[18px] font-semibold tracking-tight">
          {title}
        </h2>
      </div>
      {meta && (
        <p className="text-[11px] font-mono text-white/35 pb-1 hidden sm:block">{meta}</p>
      )}
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// Maya orb — signature element
// ───────────────────────────────────────────────────────────────────
function MayaOrb({ size = 48, live = false }: { size?: number; live?: boolean }) {
  return (
    <div
      className="relative flex-shrink-0"
      style={{ width: size, height: size }}
      aria-hidden
    >
      {live && (
        <span
          className="absolute inset-0 rounded-full mri-orb-breath"
          style={{
            background:
              "radial-gradient(circle, rgba(139,92,246,0.35) 0%, rgba(139,92,246,0) 65%)",
          }}
        />
      )}
      <span
        className="absolute inset-[18%] rounded-full"
        style={{
          background:
            "radial-gradient(circle at 35% 30%, rgba(255,255,255,0.95) 0%, #c4b5fd 22%, #8b5cf6 60%, #4c1d95 100%)",
          boxShadow:
            "0 0 22px rgba(139,92,246,0.55), inset 0 0 12px rgba(255,255,255,0.25)",
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
// Cinematic CSS — keyframes, grid, alert frame, copilot rings, RTL polish
// ───────────────────────────────────────────────────────────────────
const CINEMATIC_CSS = `
  /* Hebrew typography stack — premium-feeling system Hebrew fallback */
  .mri-hebrew {
    font-family: "Heebo", "Assistant", "Rubik", "Segoe UI", "Helvetica Neue", system-ui, sans-serif;
  }

  .mri-grid {
    background-image:
      linear-gradient(to right, rgba(139, 92, 246, 0.06) 1px, transparent 1px),
      linear-gradient(to bottom, rgba(139, 92, 246, 0.06) 1px, transparent 1px);
    background-size: 56px 56px;
    background-position: -1px -1px;
    animation: mri-grid-drift 28s linear infinite;
    mask-image: radial-gradient(ellipse 70% 60% at 50% 30%, black 35%, transparent 90%);
    -webkit-mask-image: radial-gradient(ellipse 70% 60% at 50% 30%, black 35%, transparent 90%);
    transition: opacity 900ms ease-out;
  }
  @keyframes mri-grid-drift {
    0%   { background-position: -1px -1px; }
    100% { background-position: 56px 56px; }
  }

  /* Stage entrance */
  .mri-stagger {
    opacity: 0;
    animation: mri-stage-in 700ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
  }
  @keyframes mri-stage-in {
    from { opacity: 0; transform: translateY(10px); filter: blur(6px); }
    to   { opacity: 1; transform: translateY(0);    filter: blur(0);   }
  }

  /* Stage eyebrow / sub fade-in (used per stage in Money Leak Scan) */
  .mri-stage-eyebrow {
    animation: mri-stage-in 480ms ease-out backwards;
  }

  /* Number swap-in for stage D (recoverable reveal) */
  .mri-num-swap-in {
    animation: mri-num-swap-in 600ms cubic-bezier(0.16, 1, 0.3, 1) backwards;
  }
  @keyframes mri-num-swap-in {
    from { opacity: 0; transform: translateY(10px); filter: blur(8px); }
    to   { opacity: 1; transform: translateY(0);    filter: blur(0);   }
  }

  /* Number color/shadow fade — relies on inline transition for color */
  .mri-num-fade {
    animation: mri-stage-in 380ms ease-out backwards;
  }

  /* Medical-scanner sweep line inside the verdict orb */
  .mri-scanner-line {
    background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.85) 50%, transparent 100%);
    filter: blur(0.5px);
    top: 0;
    animation: mri-scanner-line 2.6s ease-in-out infinite;
    box-shadow: 0 0 8px rgba(255,255,255,0.6);
  }
  @keyframes mri-scanner-line {
    0%   { top: 0%;   opacity: 0;   }
    10%  { opacity: 0.85; }
    50%  { top: 100%; opacity: 0.85; }
    60%  { opacity: 0;   }
    100% { top: 0%;   opacity: 0;   }
  }

  /* Severity sigil pulse */
  .mri-sev-bar { animation: mri-sev-pulse 2.6s ease-in-out infinite; }
  @keyframes mri-sev-pulse {
    0%, 100% { opacity: 1;    transform: scaleY(1); }
    50%      { opacity: 0.55; transform: scaleY(0.96); }
  }

  /* Alert chip dot — slow pulse */
  .mri-alert-dot {
    width: 5px; height: 5px; border-radius: 9999px;
    animation: mri-alert-dot-pulse 1.6s ease-in-out infinite;
  }
  @keyframes mri-alert-dot-pulse {
    0%, 100% { opacity: 1;    transform: scale(1); }
    50%      { opacity: 0.45; transform: scale(0.85); }
  }

  /* Alert-grade frame on Hero severity card — heartbeat (lub-dub then long calm) */
  .mri-alert-frame::after {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: 16px;
    pointer-events: none;
    box-shadow: inset 0 0 0 1px rgba(244,63,94,0.12);
    animation: mri-alert-heartbeat 4.8s ease-in-out infinite;
  }
  @keyframes mri-alert-heartbeat {
    /* Long calm */
    0%, 60% { box-shadow: inset 0 0 0 1px rgba(244,63,94,0.12), 0 0 0 0 rgba(244,63,94,0); }
    /* Lub */
    63%     { box-shadow: inset 0 0 0 1px rgba(244,63,94,0.42), 0 0 22px 0 rgba(244,63,94,0.25); }
    66%     { box-shadow: inset 0 0 0 1px rgba(244,63,94,0.18), 0 0 6px  0 rgba(244,63,94,0.08); }
    /* Dub */
    70%     { box-shadow: inset 0 0 0 1px rgba(244,63,94,0.36), 0 0 16px 0 rgba(244,63,94,0.18); }
    74%     { box-shadow: inset 0 0 0 1px rgba(244,63,94,0.12), 0 0 0 0 rgba(244,63,94,0); }
    /* Calm tail */
    100%    { box-shadow: inset 0 0 0 1px rgba(244,63,94,0.12), 0 0 0 0 rgba(244,63,94,0); }
  }

  /* Cinematic count-up sweep on Recoverable hero number */
  .mri-cinema-sweep {
    background: linear-gradient(110deg, transparent 0%, rgba(255,255,255,0.18) 45%, transparent 90%);
    transform: translateX(-120%);
    animation: mri-cinema-sweep 1500ms cubic-bezier(0.16,1,0.3,1) 200ms 1 both;
  }
  @keyframes mri-cinema-sweep {
    0%   { transform: translateX(-120%); }
    100% { transform: translateX(120%); }
  }

  /* Primary leak banner detect-scan line */
  .mri-detect-scan {
    background: linear-gradient(110deg, transparent 0%, rgba(244,63,94,0.10) 45%, transparent 90%);
    transform: translateX(-120%);
    animation: mri-detect-scan 4.2s ease-in-out infinite;
  }
  @keyframes mri-detect-scan {
    0%   { transform: translateX(-120%); }
    60%  { transform: translateX(120%); }
    100% { transform: translateX(120%); }
  }

  /* Maya briefing line stagger */
  .mri-briefing-line {
    opacity: 0;
    animation: mri-stage-in 600ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
  }

  /* Signal in + pulse */
  .mri-signal-in {
    opacity: 0;
    transform: translateY(4px);
    animation: mri-stage-in 500ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
  }
  .mri-signal-pulse { animation: mri-signal-ring 2.4s ease-out infinite; }
  @keyframes mri-signal-ring {
    0%   { box-shadow: 0 0 0 0   currentColor; opacity: 0.7; }
    80%  { box-shadow: 0 0 0 7px transparent;  opacity: 0;   }
    100% { box-shadow: 0 0 0 0   transparent;  opacity: 0;   }
  }

  /* Maya orb breathing */
  .mri-orb-breath { animation: mri-orb-breath 3.2s ease-in-out infinite; }
  @keyframes mri-orb-breath {
    0%, 100% { transform: scale(1);    opacity: 0.85; }
    50%      { transform: scale(1.16); opacity: 1;    }
  }

  /* Copilot listening rings — three offset rings */
  .mri-copilot-ring {
    border: 1px solid rgba(167,139,250,0.55);
    opacity: 0;
    animation: mri-copilot-ring 3s ease-out infinite;
  }
  @keyframes mri-copilot-ring {
    0%   { transform: scale(0.7); opacity: 0;    }
    20%  {                        opacity: 0.55; }
    100% { transform: scale(1.6); opacity: 0;    }
  }

  /* RTL: flip the cinema sweep + detect scan + grid drift direction so they read naturally */
  [dir="rtl"] .mri-cinema-sweep {
    background: linear-gradient(250deg, transparent 0%, rgba(255,255,255,0.18) 45%, transparent 90%);
    animation-direction: reverse;
  }
  [dir="rtl"] .mri-detect-scan {
    background: linear-gradient(250deg, transparent 0%, rgba(244,63,94,0.10) 45%, transparent 90%);
    animation-direction: reverse;
  }

  @media (prefers-reduced-motion: reduce) {
    .mri-grid,
    .mri-stagger,
    .mri-stage-eyebrow,
    .mri-num-swap-in,
    .mri-num-fade,
    .mri-scanner-line,
    .mri-sev-bar,
    .mri-alert-dot,
    .mri-alert-frame::after,
    .mri-cinema-sweep,
    .mri-detect-scan,
    .mri-briefing-line,
    .mri-signal-in,
    .mri-signal-pulse,
    .mri-orb-breath,
    .mri-copilot-ring {
      animation: none !important;
      transition: none !important;
      opacity: 1 !important;
      transform: none !important;
      filter: none !important;
    }
  }
`;

function CinematicCss() {
  return <style dangerouslySetInnerHTML={{ __html: CINEMATIC_CSS }} />;
}
