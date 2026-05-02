// /home/watch — screen strings (HE / EN).
// Shape mirrors the prototype's data-v3.js literal copy.

import type { Lang as _Lang } from "../_shared/home-strings";

export const watchStrings = {
  pageTitle: { he: "סקירה כללית", en: "Watch" },

  kpis: {
    calls: { he: "שיחות שטופלו",  en: "Calls handled" },
    leads: { he: "לידים שנלכדו",  en: "Leads captured" },
    opps:  { he: "הזדמנויות",     en: "Opportunities" },
    rev:   { he: "רווח שזוהה",    en: "Pipeline" },
    perf:  { he: "ביצועי הסוכן",  en: "Agent perf" },
    rt:    { he: "זמן תגובה",     en: "Response time" },
  },

  hero: {
    title:        { he: "מאיה ממליצה",            en: "Maya recommends" },
    why:          { he: "הפעולה המומלצת",          en: "Recommended action" },
    confidence:   { he: "ביטחון",                  en: "Confidence" },
    actionWindow: { he: "חלון פעולה",              en: "Action window" },
    expectedLift: { he: "השפעה צפויה",             en: "Expected impact" },
    primary:      { he: "אישור והפעלה",            en: "Approve & dispatch" },
    secondary:    { he: "פרטים נוספים",            en: "Show me more" },
    decline:      { he: "דחה",                     en: "Decline" },
  },

  rails: {
    voiceCalls:    { he: "שיחות קוליות חיות",      en: "Live voice calls" },
    whatsapp:      { he: "זרם וואטסאפ",            en: "WhatsApp stream" },
    leadPipeline:  { he: "צבר לידים",              en: "Lead pipeline" },
    alerts:        { he: "התראות",                 en: "Alerts" },
    insights:      { he: "תובנות",                 en: "Insights" },
    wins:          { he: "ניצחונות השבוע",          en: "Wins this week" },
    patterns:      { he: "דפוסים שזוהו",            en: "Patterns detected" },
    constellation: { he: "מערך הלקוחות",           en: "Customer constellation" },
  },

  dock: {
    placeholder: { he: "שאל את מאיה…",            en: "Ask Maya…" },
    listening:   { he: "מקשיב…",                   en: "Listening…" },
    suggestions: { he: "הצעות",                    en: "Suggestions" },
  },

  prompts: {
    morning:        { he: "מה קרה הבוקר?",           en: "What happened this morning?" },
    needAttention:  { he: "אילו לידים דורשים טיפול?", en: "Which leads need me?" },
    dropoffs:       { he: "איפה אני מאבד לקוחות?",   en: "Where am I losing deals?" },
    newOpps:        { he: "הצג לי הזדמנויות חדשות",   en: "Show new opportunities" },
  },
};

export type WatchStringKey = keyof typeof watchStrings;
