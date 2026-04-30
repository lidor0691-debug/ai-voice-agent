// Bilingual UI strings + demo-data copy for the Maya Revenue MRI Command Center.
// Kept route-local on purpose — avoids polluting the global i18n dictionary.

import type { Lang } from "@/lib/i18n";

export type MriLang = Lang;

export interface MriStrings {
  // Document chrome
  productName: string;
  productPath: string;          // "DIAGNOSE" — Maya OS path indicator
  pageTitle: string;            // "Command Center"
  patient: string;
  scan: string;
  confidence: string;
  liveChip: string;

  // Reveal sequence
  revealEyebrow: string;
  revealSteps: string[];

  // Verdict moment — Money Leak MRI Scan
  verdictEyebrow: string;
  verdictTapHint: string;
  scanFlowEyebrow: string;       // "REVENUE FLOW DETECTED"
  scanFlowSub: string;           // "monthly revenue entering system"
  scanLeakEyebrow: string;       // "DETECTING LEAKS"
  scanLeakLineLabel: (cat: string) => string;  // "Detected leak — Acceptance"
  scanEscapingEyebrow: string;   // "REVENUE CURRENTLY ESCAPING"
  scanRecoverableEyebrow: string; // "RECOVERABLE WITH MAYA"
  perMonth: string;              // "/ month" — shared

  // Hero
  heroScoreLabel: string;
  heroScoreHint: string;
  heroScoreNote: string;
  heroRecoverableLabel: string;
  heroRecoverableHint: string;
  heroRecoverableNote: string;
  heroSeverityLabel: string;
  heroSeverityHint: string;
  heroSeverityNote: string;
  heroSeverityAlertChip: string;
  heroSeverityValueCritical: string;
  heroSeverityValueHigh: string;
  heroSeverityValueModerate: string;
  heroSeverityValueLow: string;

  // Recovery projection
  recoveryEyebrow: string;
  recoveryTitle: string;
  recoveryCurrentLabel: string;
  recoveryCurrentSub: string;
  recoveryProjectedLabel: string;
  recoveryProjectedSub: string;
  recoveryToggleCurrent: string;        // "Current State"
  recoveryToggleProjected: string;      // "With Maya Optimization"
  recoveryDelta: string;

  // Leak map
  leakEyebrow: string;
  leakTitle: string;
  leakTotalPrefix: string;
  leakPerMonth: string;
  leakShareSuffix: string;
  primaryLeakEyebrow: string;
  primaryLeakLabelTpl: (label: string, share: number) => string;
  primaryLeakSub: string;

  // Diagnostic coverage
  coverageEyebrow: string;
  coverageTitle: string;
  coverageMeta: string;
  signalsAnalyzed: (n: number) => string;
  criticalFindings: (n: number) => string;
  criticalAlert: (n: number) => string;
  activeColumnTitle: string;
  activeColumnSub: string;
  passiveColumnTitle: string;
  passiveColumnSub: string;
  activeMarker: string;
  passiveMarker: string;
  signalLabels: Record<string, string>;

  // Evidence
  evidenceEyebrow: string;
  evidenceTitle: string;
  evidenceChannelLabel: string;
  evidenceTimestamp: string;
  evidenceQuote: string;
  evidenceInterpretationLabel: string;
  evidenceInterpretation: string;
  dimensionsHeader: string;
  dimensionLabels: Record<string, string>;

  // Maya briefing
  briefingEyebrow: string;
  briefingLines: string[];

  // Priority
  priorityEyebrow: string;
  priorityFocus: string;
  priorityRationale: string;
  priorityCta: string;

  // Talk to Maya
  copilotEyebrow: string;
  copilotTitle: string;
  copilotInsightLabel: string;
  copilotInsight: string;
  copilotCta: string;
  copilotListening: string;

  // Patient demo data
  patientName: string;
  patientVertical: string;

  // Footer
  footer: string;
}

const EN: MriStrings = {
  productName: "Maya Revenue MRI",
  productPath: "MAYA OS · DIAGNOSE",
  pageTitle: "Command Center",
  patient: "PATIENT",
  scan: "SCAN",
  confidence: "CONFIDENCE",
  liveChip: "Live",

  revealEyebrow: "Maya Revenue MRI · Scanning",
  revealSteps: [
    "Initializing Maya Revenue MRI",
    "Analyzing patient acquisition flow",
    "Reviewing probe evidence",
    "Calculating recoverable revenue",
    "Preparing executive diagnosis",
  ],

  verdictEyebrow: "MONEY LEAK · MRI SCAN",
  verdictTapHint: "Press space to skip",
  scanFlowEyebrow: "REVENUE FLOW DETECTED",
  scanFlowSub: "monthly revenue entering system",
  scanLeakEyebrow: "DETECTING LEAKS",
  scanLeakLineLabel: (cat) => `Detected leak — ${cat}`,
  scanEscapingEyebrow: "REVENUE CURRENTLY ESCAPING",
  scanRecoverableEyebrow: "RECOVERABLE WITH MAYA",
  perMonth: "/ month",

  heroScoreLabel: "Revenue Health Score",
  heroScoreHint: "0 — 100",
  heroScoreNote: "Below threshold for healthy acquisition.",
  heroRecoverableLabel: "Recoverable Monthly Opportunity",
  heroRecoverableHint: "Estimated · per month",
  heroRecoverableNote: "Extracted from probe evidence + leak modelling.",
  heroSeverityLabel: "Severity",
  heroSeverityHint: "Composite of all leaks",
  heroSeverityNote: "Top leakage exceeds 60% of recoverable opportunity.",
  heroSeverityAlertChip: "ACTIVE ALERT",
  heroSeverityValueCritical: "Critical",
  heroSeverityValueHigh: "High",
  heroSeverityValueModerate: "Moderate",
  heroSeverityValueLow: "Low",

  recoveryEyebrow: "RECOVERY PROJECTION",
  recoveryTitle: "Current state vs. with Maya",
  recoveryCurrentLabel: "Leaking monthly",
  recoveryCurrentSub: "Today, untreated.",
  recoveryProjectedLabel: "Recovered in 90 days",
  recoveryProjectedSub: "Maya pilot, conservative band.",
  recoveryToggleCurrent: "Current State",
  recoveryToggleProjected: "With Maya Optimization",
  recoveryDelta: "uplift",

  leakEyebrow: "LEAK MAP",
  leakTitle: "Where revenue is leaving",
  leakTotalPrefix: "Total",
  leakPerMonth: "/ month",
  leakShareSuffix: "of total",
  primaryLeakEyebrow: "PRIMARY LEAK IDENTIFIED",
  primaryLeakLabelTpl: (label, share) => `${label} · ${share}% of total leakage`,
  primaryLeakSub: "Single highest-leverage category. All downstream stages improve when this is fixed first.",

  coverageEyebrow: "DIAGNOSTIC COVERAGE",
  coverageTitle: "Multi-signal scan",
  coverageMeta: "8 surfaces · live + passive",
  signalsAnalyzed: (n) => `${n} Signals Analyzed`,
  criticalFindings: (n) => `${n} Critical Findings`,
  criticalAlert: (n) => `${n} Critical Severity Alert${n === 1 ? "" : "s"}`,
  activeColumnTitle: "Active Diagnostics",
  activeColumnSub: "Live probes — outbound test signals",
  passiveColumnTitle: "Passive Risk Models",
  passiveColumnSub: "Pattern analysis on observed traffic",
  activeMarker: "LIVE",
  passiveMarker: "PASSIVE",
  signalLabels: {
    call_response: "Call Response",
    wa_handling: "WhatsApp Lead Handling",
    booking_conv: "Booking Conversion",
    acceptance: "Acceptance Leakage",
    showup_risk: "Show-Up Risk",
    reactivation: "Reactivation Opportunity",
    referral: "Referral Leakage",
    drop_off: "Conversation Drop-Off Signals",
  },

  evidenceEyebrow: "PROBE EVIDENCE",
  evidenceTitle: "Observed conversation",
  evidenceChannelLabel: "WhatsApp · Inbound Lead",
  evidenceTimestamp: "Mar 14 · 09:47",
  evidenceQuote: "Tuesday 10am works.",
  evidenceInterpretationLabel: "Interpretation",
  evidenceInterpretation:
    "Answered, but did not qualify the lead or actively advance toward a committed consultation.",
  dimensionsHeader: "Dimension Scores",
  dimensionLabels: {
    qualification: "Qualification Quality",
    booking: "Booking Conversion",
    warmth: "Warmth",
  },

  briefingEyebrow: "MAYA BRIEFING",
  briefingLines: [
    "Primary breakdown is at acceptance.",
    "Leakage is concentrated before consult commitment.",
    "Highest-leverage move is tightening qualification on first touch.",
  ],

  priorityEyebrow: "PRIORITY MAYA FOCUS",
  priorityFocus: "Start with the highest leakage category first — Acceptance.",
  priorityRationale: "Recovers an estimated ₪67,392/mo and unblocks every downstream stage.",
  priorityCta: "Generate Pilot Plan",

  copilotEyebrow: "MAYA COPILOT",
  copilotTitle: "Talk to Maya about this MRI",
  copilotInsightLabel: "Maya Insight",
  copilotInsight: "Acceptance leakage is the highest-leverage fix. Want me to walk you through it?",
  copilotCta: "Start voice review",
  copilotListening: "Listening…",

  patientName: "Rosenfeld Aesthetics",
  patientVertical: "Med-Spa · Tel Aviv",

  footer: "MAYA · DIAGNOSE LAYER · V0.1",
};

const HE: MriStrings = {
  productName: "מאיה — אבחון הכנסות",
  productPath: "מאיה OS · אבחון",
  pageTitle: "מרכז פיקוד",
  patient: "לקוח",
  scan: "סריקה",
  confidence: "ביטחון",
  liveChip: "חי",

  revealEyebrow: "מאיה — סריקת הכנסות פעילה",
  revealSteps: [
    "מאתחלת סריקה",
    "מנתחת זרימת רכישת לקוחות",
    "סוקרת ראיות מהשטח",
    "מחשבת הכנסה ניתנת לשחזור",
    "מכינה אבחנה ניהולית",
  ],

  verdictEyebrow: "אבחון דליפת הכנסות · MRI",
  verdictTapHint: "לחיצה על רווח לדילוג",
  scanFlowEyebrow: "זוהתה זרימת הכנסות",
  scanFlowSub: "הכנסה חודשית נכנסת למערכת",
  scanLeakEyebrow: "מאתרת דליפות",
  scanLeakLineLabel: (cat) => `דליפה זוהתה — ${cat}`,
  scanEscapingEyebrow: "הכנסות בורחות כעת",
  scanRecoverableEyebrow: "ניתן להשבה עם מאיה",
  perMonth: "/ חודש",

  heroScoreLabel: "ציון בריאות הכנסות",
  heroScoreHint: "0 — 100",
  heroScoreNote: "מתחת לסף בריא ליצירת לקוחות.",
  heroRecoverableLabel: "הזדמנות חודשית להחזרת הכנסה",
  heroRecoverableHint: "אומדן · לחודש",
  heroRecoverableNote: "מבוסס על ראיות מהפרובים ומודל דליפה.",
  heroSeverityLabel: "חומרה",
  heroSeverityHint: "תרכובת של כלל הדליפות",
  heroSeverityNote: "הדליפה המובילה גדולה מ-60% מההזדמנות.",
  heroSeverityAlertChip: "התראה פעילה",
  heroSeverityValueCritical: "קריטי",
  heroSeverityValueHigh: "גבוה",
  heroSeverityValueModerate: "בינוני",
  heroSeverityValueLow: "נמוך",

  recoveryEyebrow: "תחזית התאוששות",
  recoveryTitle: "מצב נוכחי מול עבודה עם מאיה",
  recoveryCurrentLabel: "דליפה חודשית",
  recoveryCurrentSub: "כיום, ללא טיפול.",
  recoveryProjectedLabel: "מוחזר ב-90 יום",
  recoveryProjectedSub: "פיילוט מאיה, טווח שמרני.",
  recoveryToggleCurrent: "המצב הנוכחי",
  recoveryToggleProjected: "לאחר אופטימיזציית מאיה",
  recoveryDelta: "שיפור",

  leakEyebrow: "מפת דליפות",
  leakTitle: "היכן הכנסות דולפות",
  leakTotalPrefix: "סך",
  leakPerMonth: "/ חודש",
  leakShareSuffix: "מהסך הכל",
  primaryLeakEyebrow: "מקור דליפה ראשי זוהה",
  primaryLeakLabelTpl: (label, share) => `${label} · ${share}% מהדליפה הכוללת`,
  primaryLeakSub: "הקטגוריה בעלת המנוף הגבוה ביותר. תיקון ראשון כאן משחרר את כל השלבים שאחריו.",

  coverageEyebrow: "כיסוי אבחוני",
  coverageTitle: "סריקה רב-ערוצית",
  coverageMeta: "8 משטחים · חי + פסיבי",
  signalsAnalyzed: (n) => `נותחו ${n} ערוצים`,
  criticalFindings: (n) => `${n} ממצאים קריטיים`,
  criticalAlert: (n) => `${n} התראת חומרה קריטית`,
  activeColumnTitle: "אבחון פעיל",
  activeColumnSub: "פרובים חיים — שליחת אותות יזומה",
  passiveColumnTitle: "מודלים פסיביים",
  passiveColumnSub: "ניתוח דפוסים על תעבורה נצפית",
  activeMarker: "חי",
  passiveMarker: "פסיבי",
  signalLabels: {
    call_response: "מענה טלפוני",
    wa_handling: "טיפול בלידים בוואטסאפ",
    booking_conv: "המרת קביעת תור",
    acceptance: "דליפת קבלה",
    showup_risk: "סיכון אי-הגעה",
    reactivation: "הזדמנות החזרת לקוח",
    referral: "דליפת הפניות",
    drop_off: "סימני נטישת שיחה",
  },

  evidenceEyebrow: "ראיה מהשטח",
  evidenceTitle: "שיחה שנצפתה",
  evidenceChannelLabel: "וואטסאפ · ליד נכנס",
  evidenceTimestamp: "14 במרץ · 09:47",
  evidenceQuote: "יום שלישי ב-10:00 מתאים לי.",
  evidenceInterpretationLabel: "פרשנות",
  evidenceInterpretation:
    "נענה, אך לא תואם את הליד ולא הוביל באופן פעיל להתחייבות לייעוץ.",
  dimensionsHeader: "ציוני מימדים",
  dimensionLabels: {
    qualification: "איכות תיאום ציפיות",
    booking: "המרה לקביעה",
    warmth: "חום ואנושיות",
  },

  briefingEyebrow: "תדריך מאיה",
  briefingLines: [
    "השבר העיקרי הוא בשלב הקבלה.",
    "הדליפה מרוכזת לפני התחייבות לייעוץ.",
    "המהלך עם המנוף הגבוה ביותר: חידוד תיאום הציפיות בנגיעה הראשונה.",
  ],

  priorityEyebrow: "מיקוד מאיה מומלץ",
  priorityFocus: "התחילו עם הקטגוריה הדולפת ביותר — קבלה.",
  priorityRationale: "מחזיר אומדן של ₪67,392 בחודש ומשחרר את כל השלבים שאחריו.",
  priorityCta: "צור תוכנית פיילוט",

  copilotEyebrow: "מאיה קופיילוט",
  copilotTitle: "דברו עם מאיה על האבחון",
  copilotInsightLabel: "תובנת מאיה",
  copilotInsight: "דליפת הקבלה היא התיקון בעל המנוף הגבוה ביותר. רוצים שאעבור איתכם עליה?",
  copilotCta: "התחילו סקירה קולית",
  copilotListening: "מקשיבה…",

  patientName: "Rosenfeld Aesthetics",
  patientVertical: "מד-ספא · תל אביב",

  footer: "מאיה · שכבת אבחון · V0.1",
};

export const MRI_STRINGS: Record<MriLang, MriStrings> = { en: EN, he: HE };
