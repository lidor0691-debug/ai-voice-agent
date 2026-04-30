// Bilingual UI strings for the Maya Home prototype.
import type { Lang } from "@/lib/i18n";

export type HomeLang = Lang;

export interface HomeStrings {
  // Status strip
  inFlight: string;
  atRisk: string;
  inRecovery: string;
  systemsOk: string;
  systemsAlert: string;
  onWatch: string;

  // Header / orb context
  preparedAt: (time: string) => string;
  updatedAt: (time: string) => string;

  // Briefing section labels
  sectionHeadline: string;
  sectionOvernight: string;
  sectionLookAhead: string;
  sectionWrap: string;

  // Decisions
  decisionsHeader: (n: number) => string;
  decisionsAllClear: string;
  decisionApprove: string;
  decisionOverride: string;
  decisionWatching: string;
  decisionContextLabel: string;
  decisionRecommendLabel: string;
  decisionRationaleLabel: string;
  decisionRecovers: (n: string) => string;
  decisionApproved: string;

  // Missions
  missionsHeader: string;
  missionWeek: (curr: number, total: number) => string;
  missionOpen: string;

  // Command palette
  paletteOpenHint: string;
  palettePlaceholder: string;
  paletteEmpty: string;
  paletteGroupLead: string;
  paletteGroupMission: string;
  paletteGroupBriefing: string;
  paletteGroupAction: string;

  // Night watch
  nightWatchTitle: string;
  nightWatchSub: (open: number, queued: number) => string;
  nightWatchPolicy: string;
  nightWatchTakeOver: string;

  // Demo controls
  demoLabel: string;
  demoModeDay: string;
  demoModeNight: string;
}

const EN: HomeStrings = {
  inFlight: "in flight",
  atRisk: "at risk",
  inRecovery: "in recovery",
  systemsOk: "all systems",
  systemsAlert: "system check",
  onWatch: "On Watch",

  preparedAt: (t) => `prepared ${t}`,
  updatedAt: (t) => `updated ${t}`,

  sectionHeadline: "Headline",
  sectionOvernight: "Overnight",
  sectionLookAhead: "Look ahead",
  sectionWrap: "Wrap",

  decisionsHeader: (n) => `Decisions · ${n}`,
  decisionsAllClear: "Nothing for you right now.",
  decisionApprove: "Approve",
  decisionOverride: "Override",
  decisionWatching: "Watching",
  decisionContextLabel: "Context",
  decisionRecommendLabel: "Maya recommends",
  decisionRationaleLabel: "Why",
  decisionRecovers: (n) => `recovers ~${n}`,
  decisionApproved: "Maya is on it",

  missionsHeader: "Active missions",
  missionWeek: (c, t) => `week ${c} / ${t}`,
  missionOpen: "Open",

  paletteOpenHint: "⌘ K",
  palettePlaceholder: "Search a lead, mission, briefing, or action…",
  paletteEmpty: "Nothing matches.",
  paletteGroupLead: "Leads",
  paletteGroupMission: "Missions",
  paletteGroupBriefing: "Briefings",
  paletteGroupAction: "Actions",

  nightWatchTitle: "Maya is on watch tonight",
  nightWatchSub: (o, q) => `${o} conversations open · ${q} reminders queued for 07:00`,
  nightWatchPolicy: "I'll handle these unless you want to step in.",
  nightWatchTakeOver: "Take over",

  demoLabel: "Demo",
  demoModeDay: "Day",
  demoModeNight: "Night",
};

const HE: HomeStrings = {
  inFlight: "פעילים",
  atRisk: "בסיכון",
  inRecovery: "בשיקום",
  systemsOk: "המערכות תקינות",
  systemsAlert: "דרושה בדיקה",
  onWatch: "במשמרת",

  preparedAt: (t) => `הוכן ב-${t}`,
  updatedAt: (t) => `עודכן ב-${t}`,

  sectionHeadline: "כותרת",
  sectionOvernight: "הלילה",
  sectionLookAhead: "מבט קדימה",
  sectionWrap: "סיכום היום",

  decisionsHeader: (n) => `החלטות · ${n}`,
  decisionsAllClear: "אין דבר שדורש אותך כרגע.",
  decisionApprove: "אישור",
  decisionOverride: "החלפה",
  decisionWatching: "במעקב",
  decisionContextLabel: "הקשר",
  decisionRecommendLabel: "ההמלצה של מאיה",
  decisionRationaleLabel: "למה",
  decisionRecovers: (n) => `מחזיר ~${n}`,
  decisionApproved: "מאיה מטפלת",

  missionsHeader: "משימות פעילות",
  missionWeek: (c, t) => `שבוע ${c} / ${t}`,
  missionOpen: "פתח",

  paletteOpenHint: "⌘ K",
  palettePlaceholder: "חיפוש ליד, משימה, תדריך או פעולה…",
  paletteEmpty: "לא נמצאו תוצאות.",
  paletteGroupLead: "לידים",
  paletteGroupMission: "משימות",
  paletteGroupBriefing: "תדריכים",
  paletteGroupAction: "פעולות",

  nightWatchTitle: "מאיה במשמרת הלילה",
  nightWatchSub: (o, q) => `${o} שיחות פתוחות · ${q} תזכורות מוכנות ל-07:00`,
  nightWatchPolicy: "אטפל בהן אלא אם תרצה להתערב.",
  nightWatchTakeOver: "השתלטות",

  demoLabel: "הדגמה",
  demoModeDay: "יום",
  demoModeNight: "לילה",
};

export const HOME_STRINGS: Record<HomeLang, HomeStrings> = { en: EN, he: HE };
