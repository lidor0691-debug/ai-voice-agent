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
    ownerFirstName: "Lior",
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
        "Acceptance dropped 18% over the last three nights.",
        "Three high-profile leads went untouched after 22:00.",
        "I have proposals for two of them.",
      ],
      overnight: [
        { text: "23 inbound · 19 closed cleanly", emphasis: "fact" },
        { text: "4 stalled at qualification — 3 high-profile (see Decisions)", emphasis: "fact" },
        { text: "6 reminders sent for today — all confirmed", emphasis: "fact" },
        {
          text: "You overrode my call on Sarah Cohen yesterday — she booked at 11:15 today.",
          emphasis: "note",
          yesterdayCallback: true,
        },
      ],
      lookAhead: [
        { text: "11 consults today · 2 first-time", emphasis: "fact" },
        { text: "Slow stretch expected 14:00–16:00", emphasis: "estimate" },
        { text: "Dr. Roth ends at 18:30 — 2 candidate slots open after that", emphasis: "estimate" },
      ],
    },
    decisions: [
      {
        id: "d-sarah",
        tone: "recommend",
        who: "Sarah Cohen",
        context: "High-LTV lead, hesitated last night after price exchange.",
        recommendation: "Send the 15% first-consult offer via WhatsApp now.",
        rationale: "She's the profile that converts at 64% with this incentive in our data.",
        channel: "WhatsApp · last seen 22:14",
        recoveredEstimate: 1850,
      },
      {
        id: "d-yossi",
        tone: "recommend",
        who: "Yossi Levy",
        context: "Stalled at qualification — asked about availability twice, no follow-through.",
        recommendation: "Offer Tuesday or Thursday morning, lead with the time, then the price.",
        rationale: "His pattern matches three recoverable leads from last month.",
        channel: "WhatsApp · last seen 23:47",
        recoveredEstimate: 1500,
      },
      {
        id: "d-watch",
        tone: "watching",
        who: "Daniel Bar",
        context: "Replied to a reminder but didn't confirm — appointment in 4 hours.",
        recommendation: "Watching — I'll send a confirmation nudge at 11:30 unless he replies first.",
        channel: "WhatsApp · 09:02",
      },
    ],
    missions: [
      {
        id: "m-acceptance",
        name: "Acceptance Recovery",
        weekCurrent: 2,
        weekTotal: 4,
        capturedLabel: "₪14,200 / ₪67,000",
        spark: [0.05, 0.10, 0.12, 0.18, 0.22, 0.25, 0.30, 0.34, 0.41, 0.47, 0.51, 0.58, 0.63, 0.68],
        emphasis: "active",
      },
      {
        id: "m-reactivation",
        name: "Reactivation Q4",
        weekCurrent: 6,
        weekTotal: 8,
        capturedLabel: "41 patients re-engaged",
        spark: [0.20, 0.28, 0.35, 0.40, 0.42, 0.46, 0.55, 0.58, 0.62, 0.68, 0.72, 0.78, 0.82, 0.86],
        emphasis: "active",
      },
    ],
    paletteItems: [
      { id: "p1", group: "lead", title: "Sarah Cohen", subtitle: "WhatsApp · last 22:14", hint: "Lead" },
      { id: "p2", group: "lead", title: "Yossi Levy", subtitle: "WhatsApp · last 23:47", hint: "Lead" },
      { id: "p3", group: "lead", title: "Daniel Bar", subtitle: "WhatsApp · 09:02 today", hint: "Lead" },
      { id: "p4", group: "mission", title: "Acceptance Recovery", subtitle: "Week 2 / 4", hint: "Mission" },
      { id: "p5", group: "mission", title: "Reactivation Q4", subtitle: "Week 6 / 8", hint: "Mission" },
      { id: "p6", group: "briefing", title: "Yesterday's brief", subtitle: "Mon 10 Nov · prepared 06:11", hint: "Brief" },
      { id: "p7", group: "briefing", title: "Last week's brief — Mon", subtitle: "04 Nov · prepared 06:18", hint: "Brief" },
      { id: "p8", group: "action", title: "Run a Revenue MRI", subtitle: "Diagnose mode", hint: "Action" },
      { id: "p9", group: "action", title: "Adjust Maya's autonomy", subtitle: "Currently: assisted (medium)", hint: "Action" },
      { id: "p10", group: "action", title: "Switch language", subtitle: "Hebrew ↔ English", hint: "Action" },
    ],
  };
}
