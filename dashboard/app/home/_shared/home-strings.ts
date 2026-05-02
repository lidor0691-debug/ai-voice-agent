// Shared strings for the entire /home/* surface.
// Per-screen strings live alongside each screen (e.g. watch-strings.ts).

export type Lang = "he" | "en";

export const homeStrings = {
  appName: { he: "מאיה", en: "Maya" },
  appTagline: { he: "לוח בקרה חכם", en: "Command center" },

  nav: {
    watch:     { he: "סקירה כללית", en: "Watch" },
    calls:     { he: "שיחות קוליות", en: "Voice calls" },
    whatsapp:  { he: "וואטסאפ",      en: "WhatsApp" },
    leads:     { he: "לידים",         en: "Leads" },
    insights:  { he: "תובנות",        en: "Insights" },
    agents:    { he: "סוכנים",        en: "Agents" },
    automate:  { he: "אוטומציות",     en: "Automations" },
    reports:   { he: "דוחות",         en: "Reports" },
    settings:  { he: "הגדרות",        en: "Settings" },
  },

  common: {
    live:        { he: "חי",        en: "Live" },
    new:         { he: "חדש",       en: "New" },
    open:        { he: "פתח",       en: "Open" },
    approve:     { he: "אישור",     en: "Approve" },
    decline:     { he: "דחייה",     en: "Decline" },
    delegate:    { he: "האצל",      en: "Delegate" },
    askMaya:     { he: "שאל את מאיה…", en: "Ask Maya…" },
    listening:   { he: "מקשיב",     en: "Listening" },
    speaking:    { he: "מדבר",       en: "Speaking" },
    confidence:  { he: "ביטחון",    en: "Confidence" },
    impact:      { he: "השפעה",     en: "Impact" },
    window:      { he: "חלון פעולה", en: "Action window" },
  },
};

export type HomeNavKey = keyof typeof homeStrings.nav;

export const NAV_ORDER: { key: HomeNavKey; href: string; wired: boolean }[] = [
  { key: "watch",     href: "/home/watch",     wired: true  },
  { key: "calls",     href: "/home/calls",     wired: true  },
  { key: "whatsapp",  href: "/home/whatsapp",  wired: false },
  { key: "leads",     href: "/home/leads",     wired: true  },
  { key: "insights",  href: "/home/insights",  wired: true  },
  { key: "agents",    href: "/home/agents",    wired: true  },
  { key: "automate",  href: "/home/automate",  wired: false },
  { key: "reports",   href: "/home/reports",   wired: false },
  { key: "settings",  href: "/home/settings",  wired: false },
];
