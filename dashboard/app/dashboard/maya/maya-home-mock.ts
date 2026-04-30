// Mock dataset for the Maya Home prototype. Mirrors the shape we'd expect from
// a real briefing pipeline. No backend coupling — purely UI data.

export type OrbState = "idle" | "working" | "watching" | "heard";

export interface InstrumentState {
  inFlight: number;     // leads/conversations currently active
  atRisk: number;       // today's bookings predicted to no-show, etc.
  inRecovery: number;   // ₪ in active recovery missions
  systemsOk: boolean;
}

export interface BriefingItem {
  // structured line for OVERNIGHT / LOOK AHEAD lists
  text: string;
  emphasis?: "fact" | "estimate" | "note"; // typography signal
  yesterdayCallback?: boolean; // continuity with yesterday
}

export interface Briefing {
  preparedAt: string;       // ISO
  updatedAt: string;        // ISO — for the live "edited in place" feel
  headlineLines: string[];  // 1-3 sentences
  overnight: BriefingItem[];
  lookAhead: BriefingItem[];
}

export type DecisionTone = "recommend" | "watching" | "urgent";

export interface Decision {
  id: string;
  tone: DecisionTone;
  who: string;                // e.g. "Sarah Cohen"
  context: string;            // 1-line situation
  recommendation: string;     // Maya's proposed action
  rationale?: string;         // optional "why" line
  channel?: string;           // "WhatsApp · 22:14" — chrome
  recoveredEstimate?: number; // ₪ if executed
}

export interface Mission {
  id: string;
  name: string;
  weekCurrent: number;
  weekTotal: number;
  capturedLabel: string;   // "₪14,200 / ₪67,000" or "41 patients"
  spark: number[];         // 14 normalized 0..1 values for the trend
  emphasis?: "active" | "complete";
}

export interface MayaHomeData {
  ownerFirstName: string;
  clinicName: string;
  date: string;            // ISO date
  instruments: InstrumentState;
  briefing: Briefing;
  decisions: Decision[];
  missions: Mission[];
  // For "Cmd-K" mock — searchable items
  paletteItems: PaletteItem[];
}

export interface PaletteItem {
  id: string;
  group: "lead" | "mission" | "briefing" | "action";
  title: string;
  subtitle?: string;
  hint?: string; // e.g. "Yesterday's brief"
}

export function getMockHome(): MayaHomeData {
  return {
    ownerFirstName: "לידור",
    clinicName: "Rosenfeld Aesthetics",
    date: new Date().toISOString(),
    instruments: {
      inFlight: 14,
      atRisk: 3,
      inRecovery: 31400,
      systemsOk: true,
    },
    briefing: {
      preparedAt: new Date(new Date().setHours(6, 15, 0, 0)).toISOString(),
      updatedAt: new Date().toISOString(),
      headlineLines: [
        "שיעור הקבלה ירד ב-18% בשלושת הלילות האחרונים.",
        "שלושה לידים חמים נשארו ללא מענה אחרי 22:00.",
        "לשניים מהם יש לי הצעה מוכנה.",
      ],
      overnight: [
        { text: "23 פניות נכנסות · 19 נסגרו תקין", emphasis: "fact" },
        { text: "4 נתקעו בסינון — 3 חמים (פירוט בהחלטות)", emphasis: "fact" },
        { text: "6 תזכורות לפגישות היום נשלחו — כולן אושרו", emphasis: "fact" },
        {
          text: "אתמול בחרת אחרת לגבי שרה כהן — והיא קבעה היום ב-11:15.",
          emphasis: "note",
          yesterdayCallback: true,
        },
      ],
      lookAhead: [
        { text: "11 ייעוצים היום · 2 חדשים", emphasis: "fact" },
        { text: "צפויה רגיעה בין 14:00 ל-16:00", emphasis: "estimate" },
        { text: "ד״ר רוט מסיימת ב-18:30 — שני זמנים פנויים אחר כך", emphasis: "estimate" },
      ],
    },
    decisions: [
      {
        id: "d-sarah",
        tone: "recommend",
        who: "שרה כהן",
        context: "לקוחה בערך גבוה. היססה אתמול אחרי שיחה על מחיר.",
        recommendation: "שלחי לה עכשיו את הצעת ה-15% לייעוץ ראשון בוואטסאפ.",
        rationale: "פרופיל שממיר אצלנו ב-64% עם תמריץ כזה.",
        channel: "וואטסאפ · נראתה לאחרונה 22:14",
        recoveredEstimate: 1850,
      },
      {
        id: "d-yossi",
        tone: "recommend",
        who: "יוסי לוי",
        context: "נתקע בסינון. שאל פעמיים על זמינות בלי להתקדם.",
        recommendation: "הציעי שלישי או חמישי בבוקר. פתחי עם הזמן, ורק אחר כך המחיר.",
        rationale: "הדפוס שלו תואם שלושה לידים שהחזרנו בחודש שעבר.",
        channel: "וואטסאפ · נראה לאחרונה 23:47",
        recoveredEstimate: 1500,
      },
      {
        id: "d-watch",
        tone: "watching",
        who: "דניאל בר",
        context: "ענה לתזכורת בלי לאשר. תור עוד 4 שעות.",
        recommendation: "אשלח לו תזכורת אישור ב-11:30 אם לא יחזור אלי קודם.",
        channel: "וואטסאפ · 09:02",
      },
    ],
    missions: [
      {
        id: "m-acceptance",
        name: "שיקום שלב הקבלה",
        weekCurrent: 2,
        weekTotal: 4,
        capturedLabel: "₪14,200 / ₪67,000",
        spark: [0.05, 0.10, 0.12, 0.18, 0.22, 0.25, 0.30, 0.34, 0.41, 0.47, 0.51, 0.58, 0.63, 0.68],
        emphasis: "active",
      },
      {
        id: "m-reactivation",
        name: "החזרת לקוחות Q4",
        weekCurrent: 6,
        weekTotal: 8,
        capturedLabel: "41 לקוחות שוחזרו",
        spark: [0.20, 0.28, 0.35, 0.40, 0.42, 0.46, 0.55, 0.58, 0.62, 0.68, 0.72, 0.78, 0.82, 0.86],
        emphasis: "active",
      },
    ],
    paletteItems: [
      { id: "p1", group: "lead", title: "שרה כהן", subtitle: "וואטסאפ · 22:14", hint: "ליד" },
      { id: "p2", group: "lead", title: "יוסי לוי", subtitle: "וואטסאפ · 23:47", hint: "ליד" },
      { id: "p3", group: "lead", title: "דניאל בר", subtitle: "וואטסאפ · 09:02", hint: "ליד" },
      { id: "p4", group: "mission", title: "שיקום שלב הקבלה", subtitle: "שבוע 2 / 4", hint: "משימה" },
      { id: "p5", group: "mission", title: "החזרת לקוחות Q4", subtitle: "שבוע 6 / 8", hint: "משימה" },
      { id: "p6", group: "briefing", title: "התדריך של אתמול", subtitle: "ב', 10 בנובמבר · הוכן 06:11", hint: "תדריך" },
      { id: "p7", group: "briefing", title: "תדריך שבוע שעבר — שני", subtitle: "4 בנובמבר · הוכן 06:18", hint: "תדריך" },
      { id: "p8", group: "action", title: "הרץ אבחון הכנסות", subtitle: "מצב אבחון", hint: "פעולה" },
      { id: "p9", group: "action", title: "כיוון רמת אוטונומיה", subtitle: "כרגע: עם סיוע (בינוני)", hint: "פעולה" },
      { id: "p10", group: "action", title: "החלפת שפה", subtitle: "עברית ↔ אנגלית", hint: "פעולה" },
    ],
  };
}
