// /home/watch — mock dataset.
// Mirrors the prototype's data-v3.js so the visual is faithful.
// The shell can swap this for a real API response — types stay the same.

export type KpiTrend = "up" | "down" | "flat";

export interface Kpi {
  key: "calls" | "leads" | "opps" | "rev" | "perf" | "rt";
  label: string;
  value: string;
  delta: string;
  dir: KpiTrend;
}

export interface VoiceCall {
  id: string;
  who: string;
  meta: string;
  agent: string;
  duration: string;
  live: boolean;
}

/** Delivery state derived from Maya Watch followup_status + followup_error_code. */
export interface DeliveryInfo {
  /** Hebrew label, e.g. "נמסר", "נכשל". */
  label: string;
  /** Color tone for the indicator: green / amber / neutral. */
  tone: "ok" | "warn" | "neutral";
  /** Optional Hebrew error string when delivery failed. */
  errorLabel?: string;
}

/** A single message inside a WhatsApp thread (compact + modal share this shape). */
export interface WhatsAppMessage {
  direction: "in" | "out";
  body: string;
  /** Relative time string for display, e.g. "12 דק׳". */
  ago: string;
  /** Short Hebrew verb prefix: "שאל" (asked), "שלחה" (sent), "ענה" (replied). */
  prefix: string;
  /** Optional ISO timestamp — used in the timeline modal when present. */
  ts?: string;
}

export interface WhatsAppThread {
  id: string;
  who: string;
  preview: string;
  ago: string;
  by: "AI" | "human";
  unread: boolean;
  /** Present when this thread has an outgoing Maya followup with a known delivery state. */
  delivery?: DeliveryInfo;
  /** Bare lead/customer name without any sender prefix — used as modal header. */
  leadName?: string;
  /**
   * Chronological message list (oldest first). When present, the panel renders
   * a compact conversation view; when absent, falls back to single-preview style.
   */
  messages?: WhatsAppMessage[];
  /**
   * Set when the latest customer message arrived more than 24h after Maya's
   * last followup — the followup is "stale" and should be shown as historical
   * context (not as an active reply). Example:
   *   "הודעת שחזור קודמת נשלחה לפני יום"
   * Combined with delivery.label by the panel into:
   *   "הודעת שחזור קודמת נשלחה לפני יום · נמסר"
   */
  staleFollowupNote?: string;
}

export interface LeadStage {
  stage: string;
  n: number;
  pct: number;
}

export type OrbitState = "hot" | "warm" | "cool";

export interface OrbitNode {
  id: string;
  name: string;
  value: string;
  r: number;
  theta: number;
  state: OrbitState;
  label: string;
}

export interface HeroRecommendation {
  /** Backend decision id of the form `decision:{status}:{phone}`. Present
   *  only on live mappings — quiet-live, fetch-failed, and demo states
   *  leave it undefined and the action button is rendered disabled. */
  id?: string;
  /** Lead phone number (E.164). Present alongside `id` on live mappings. */
  phone?: string;
  target: string;
  value: string;
  headline: string;
  why: string[];
  action: string;
  confidence: number;
  window: string;
  impact: string;
  /** Present when the lead matching this recommendation has a known delivery state. */
  delivery?: {
    /** Full Hebrew sentence, e.g. "הודעת השחזור נמסרה" or "הודעת השחזור לא נמסרה — מחוץ לחלון...". */
    label: string;
    tone: "ok" | "warn";
  };
}

export type AlertSeverity = "high" | "med" | "low";

export interface Alert {
  id: string;
  severity: AlertSeverity;
  ago: string;
  who: string;
  body: string;
}

export interface Insight {
  head: string;
  body: string;
  conf: number;
}

export interface Win {
  name: string;
  desc: string;
  value: string;
}

export interface Pattern {
  head: string;
  body: string;
}

export interface AgentToday {
  label: string;
  value: string;
}

export interface WatchData {
  user: { name: string; role: string };
  kpis: Kpi[];
  hero: HeroRecommendation;
  calls: VoiceCall[];
  whatsapp: WhatsAppThread[];
  leads: LeadStage[];
  orbits: OrbitNode[];
  alerts: Alert[];
  insights: Insight[];
  wins: Win[];
  patterns: Pattern[];
  agentToday: AgentToday[];
  prompts: string[];
}

export const watchMock: WatchData = {
  user: { name: "יואב כהן", role: "בעל העסק" },

  kpis: [
    { key: "calls", label: "שיחות שטופלו", value: "247",   delta: "+18%",   dir: "up" },
    { key: "leads", label: "לידים שנלכדו",  value: "62",    delta: "+24%",   dir: "up" },
    { key: "opps",  label: "הזדמנויות",     value: "27",    delta: "+9%",    dir: "up" },
    { key: "rev",   label: "רווח שזוהה",    value: "₪284K", delta: "+12.4%", dir: "up" },
    { key: "perf",  label: "ביצועי הסוכן",  value: "98.6%", delta: "+0.4%",  dir: "up" },
    { key: "rt",    label: "זמן תגובה",     value: "11ש'",  delta: "−2ש'",   dir: "up" },
  ],

  hero: {
    target: "אפרצ׳ר ביו",
    value: "₪420K",
    headline: "אפרצ׳ר ביו עומדת לסגור עסקה",
    why: [
      "סמנכ״ל הפיתוח ביקר בדף התמחור 4 פעמים בשעתיים האחרונות",
      "התבנית תואמת ל־11 מתוך 12 העסקאות האחרונות שנסגרו",
      "צוות הפיתוח גדל ב־40% ברבעון",
    ],
    action: "הפעלת סוכן קולי 03 לשיחת גילוי",
    confidence: 87,
    window: "חלון פעולה: 6 שעות",
    impact: "+₪420K צפוי",
  },

  calls: [
    { id: "c1", who: "נועה לוי",  meta: "אפרצ׳ר ביו · גילוי", agent: "סוכן קולי 03", duration: "00:42", live: true },
    { id: "c2", who: "אלי כהן",   meta: "הליקס · הדגמה",       agent: "סוכן קולי 01", duration: "01:15", live: true },
    { id: "c3", who: "דניאל ברק", meta: "קובלט · חידוש",       agent: "סוכן קולי 02", duration: "00:31", live: true },
  ],

  whatsapp: [
    { id: "w1", who: "יואב לוי",    preview: "מצוין, נסגור יום שישי ב־11:00. תודה!",    ago: "06:41", by: "AI",    unread: true  },
    { id: "w2", who: "מיכל כהן",    preview: "אפשר לקבל דף הביטחון לפני המחר?",         ago: "06:18", by: "AI",    unread: true  },
    { id: "w3", who: "רון ישראלי",  preview: "אישרתי את ההצעה. מעביר לחתימה.",          ago: "05:52", by: "human", unread: false },
    { id: "w4", who: "טל אברהם",    preview: "לא בזמן הנכון, נדבר ברבעון הבא.",          ago: "04:30", by: "AI",    unread: false },
  ],

  leads: [
    { stage: "חדשים",      n: 124, pct: 1.0  },
    { stage: "ביצירת קשר", n: 86,  pct: 0.69 },
    { stage: "מוסמכים",    n: 41,  pct: 0.33 },
    { stage: "הדגמה",      n: 18,  pct: 0.15 },
    { stage: "סגירה",      n: 9,   pct: 0.07 },
  ],

  orbits: [
    { id: "o1", name: "אפרצ׳ר ביו",     value: "₪420K", r: 0.82, theta: -0.35, state: "hot",  label: "הזדמנות חמה" },
    { id: "o2", name: "וולה אינדוסטריז", value: "₪320K", r: 0.85, theta:  0.55, state: "warm", label: "במעקב" },
    { id: "o3", name: "קובלט נטוורקס",  value: "₪220K", r: 0.78, theta: -1.30, state: "warm", label: "בסיכון" },
    { id: "o4", name: "הליקס לאבס",     value: "₪190K", r: 0.92, theta:  1.95, state: "hot",  label: "הזדמנות חדשה" },
    { id: "o5", name: "נורת'ווינד",      value: "₪280K", r: 0.72, theta:  2.85, state: "warm", label: "RFP בצהריים" },
    { id: "o6", name: "צ׳רי־01",         value: "₪140K", r: 0.62, theta: -2.15, state: "cool", label: "פעיל" },
    { id: "o7", name: "ברייטפאת'",       value: "₪180K", r: 0.55, theta: -2.65, state: "cool", label: "סגר השבוע" },
    { id: "o8", name: "וורידיאן",        value: "₪520K", r: 0.50, theta:  0.18, state: "cool", label: "סגר היום" },
  ],

  alerts: [
    { id: "a1", severity: "high", ago: "5 דק׳",  who: "ירידה במעורבות",   body: "שיעור הפתיחה במייל ירד ב־17% בשעה האחרונה" },
    { id: "a2", severity: "med",  ago: "12 דק׳", who: "ליד חדש חם",         body: "ולה אינדוסטריז גייסה 40 מיליון דולר — בתוך ה־ICP" },
    { id: "a3", severity: "low",  ago: "34 דק׳", who: "הזדמנות שלא נענתה", body: "3 לידים זקוקים למעקב מצוות המכירות" },
  ],

  insights: [
    {
      head: "לידים משימושי מנועי חיפוש סוגרים פי 2.3 מהר יותר",
      body: "לידים שמגיעים דרך גוגל בקטגוריית B2B נוטים להגיב תוך 4 שעות בממוצע.",
      conf: 0.86,
    },
  ],

  wins: [
    { name: "ורידיאן",     desc: "סגירת עסקה",     value: "₪524K" },
    { name: "קובלט בע״מ",  desc: "חידוש שנתי",     value: "₪318K" },
    { name: "הליקס לאבס",  desc: "הצעת מחיר אושרה", value: "₪257K" },
  ],

  patterns: [
    { head: "שיחות אחה״צ סוגרות יותר",     body: "שיחות בין 14:00-16:00 מובילות לסגירה ב־34% יותר מקרים" },
    { head: "הודעות וואטסאפ קצרות עובדות", body: "תגובות מתחת ל־120 תווים — שיעור מענה גבוה ב־41%" },
  ],

  agentToday: [
    { label: "שיחות יוצאות", value: "5/8" },
    { label: "שיחות נכנסות",  value: "4/6" },
    { label: "וואטסאפ",       value: "38" },
  ],

  prompts: [
    "מה קרה הבוקר?",
    "אילו לידים דורשים טיפול?",
    "איפה אני מאבד לקוחות?",
    "הצג לי הזדמנויות חדשות",
  ],
};
