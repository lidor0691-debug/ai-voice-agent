// /home/watch — live data bridge.
// Fetches the production Maya Watch endpoints, maps responses into the
// existing WatchData shape, and degrades to the mock when the API is
// unreachable or empty.

import {
  watchMock,
  type WatchData,
  type Kpi,
  type HeroRecommendation,
  type OrbitNode,
  type OrbitState,
  type WhatsAppThread,
  type Alert,
  type AlertSeverity,
  type LeadStage,
} from "./watch-mock";

const BASE = "https://ai-voice-agent-production-0a55.up.railway.app";
const TIMEOUT_MS = 5000;

// Backend currently has no per-lead value. Use a temporary estimate per
// engaged lead so the UI has something to display until pricing lands.
const TEMP_VALUE_LABEL = "₪1,850";
const TEMP_VALUE_NUM = 1850;

// ── Loose API types — every field is optional so a malformed payload
//    can't crash the mapper.
interface ApiCounts {
  total_leads?: number;
  at_risk?: number;
  followup_pending?: number;
  replied_after_followup?: number;
  booked?: number;
  no_response?: number;
}

interface ApiDecision {
  id?: string;
  phone?: string;
  lead_name?: string;
  status?: string;
  situation?: string;
  why_it_matters?: string;
  recommendation?: string;
  suggested_message?: string;
  confidence?: string;
  value_hint?: string;
}

interface ApiBriefing {
  headline?: string;
  summary_bullets?: string[];
  decisions?: ApiDecision[];
  counts?: ApiCounts;
}

interface ApiTimedBody {
  body?: string;
  ts?: string;
}

interface ApiLead {
  phone?: string;
  name?: string;
  status?: string;
  message_count?: number;
  last_inbound?: ApiTimedBody | null;
  last_outbound?: ApiTimedBody | null;
  followup_sent_at?: string | null;
  followup_body?: string | null;
  booked?: boolean;
  booked_at?: string | null;
}

interface ApiLeadsResp {
  leads?: ApiLead[];
}

export interface MayaWatchLive {
  briefing: ApiBriefing;
  leads: ApiLead[];
}

/** Optional auth-derived identity. When absent, falls back to neutral product identity. */
export interface AuthIdentity {
  name?: string | null;
  role?: string | null;
}

const PRODUCT_IDENTITY = { name: "Maya Watch", role: "מצב חי" } as const;

/**
 * Resolve the bottom-rail identity. Live mode never shows the mock person —
 * if no real identity is available it shows the neutral product identity.
 */
function resolveLiveIdentity(identity?: AuthIdentity): { name: string; role: string } {
  const name = identity?.name?.trim();
  const role = identity?.role?.trim();
  if (name && role) return { name, role };
  if (name)         return { name, role: PRODUCT_IDENTITY.role };
  if (role)         return { name: PRODUCT_IDENTITY.name, role };
  return { ...PRODUCT_IDENTITY };
}

// ── Fetch ─────────────────────────────────────────────────────────────

async function fetchJSON<T>(path: string): Promise<T> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE}${path}`, {
      signal: ctrl.signal,
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`${path}: ${res.status} ${res.statusText}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(t);
  }
}

/** Returns null on any network/parse error so callers can fall back to mock. */
export async function fetchMayaWatch(): Promise<MayaWatchLive | null> {
  try {
    const [briefing, leadsResp] = await Promise.all([
      fetchJSON<ApiBriefing>("/maya-watch/briefing"),
      fetchJSON<ApiLeadsResp>("/maya-watch/leads"),
    ]);
    return { briefing: briefing ?? {}, leads: leadsResp?.leads ?? [] };
  } catch (e) {
    console.warn("[/home/watch] live fetch failed, using mock:", e);
    return null;
  }
}

// ── Helpers ───────────────────────────────────────────────────────────

function safeCounts(c?: ApiCounts): Required<ApiCounts> {
  return {
    total_leads: c?.total_leads ?? 0,
    at_risk: c?.at_risk ?? 0,
    followup_pending: c?.followup_pending ?? 0,
    replied_after_followup: c?.replied_after_followup ?? 0,
    booked: c?.booked ?? 0,
    no_response: c?.no_response ?? 0,
  };
}

function relativeAgo(ts?: string | null): string {
  if (!ts) return "—";
  const t = new Date(ts).getTime();
  if (isNaN(t)) return "—";
  const diffMs = Date.now() - t;
  if (diffMs < 0) return "עכשיו";
  const min = Math.floor(diffMs / 60000);
  if (min < 1) return "עכשיו";
  if (min < 60) return `${min} דק׳`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} שע׳`;
  const day = Math.floor(hr / 24);
  return `${day} ימים`;
}

function statusToOrbitState(status?: string): OrbitState {
  switch (status) {
    case "replied_after_followup":
      return "hot";
    case "at_risk":
    case "no_response":
    case "followup_pending":
      return "warm";
    case "booked":
      return "cool";
    default:
      return "warm";
  }
}

function statusToSeverity(status?: string): AlertSeverity {
  switch (status) {
    case "replied_after_followup":
    case "at_risk":
      return "high";
    case "followup_pending":
      return "med";
    default:
      return "low";
  }
}

function statusLabelHe(status?: string): string {
  switch (status) {
    case "replied_after_followup": return "חזר אחרי שחזור";
    case "at_risk":                return "בסיכון";
    case "followup_pending":       return "ממתין למעקב";
    case "booked":                 return "תואם";
    case "no_response":            return "לא ענה";
    default:                       return status ?? "—";
  }
}

function confidenceToPct(c?: string): number {
  const v = (c ?? "").toLowerCase().slice(0, 3);
  if (v === "hig") return 90;
  if (v === "med") return 65;
  if (v === "low") return 40;
  return 70;
}

function leadDisplayName(l: ApiLead): string {
  if (l.name && l.name.trim()) return l.name.trim();
  const phone = l.phone ?? "";
  return phone ? `ליד ${phone.slice(-4)}` : "ליד";
}

function clamp(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, n));
}

// ── Builders ──────────────────────────────────────────────────────────

function buildKpisFromCounts(counts: Required<ApiCounts>): Kpi[] {
  const replied = counts.replied_after_followup;
  const booked = counts.booked;
  const engaged = replied + booked;
  const estValue = engaged * TEMP_VALUE_NUM;
  const fmtValue =
    estValue >= 1000 ? `₪${(estValue / 1000).toFixed(1)}K` : estValue > 0 ? `₪${estValue}` : "—";
  return [
    { key: "calls", label: "סך לידים",      value: String(counts.total_leads),         delta: "—", dir: "flat" },
    { key: "leads", label: "חזרו אחרי שחזור", value: String(replied),                    delta: "—", dir: replied > 0 ? "up" : "flat" },
    { key: "opps",  label: "ממתין למעקב",   value: String(counts.followup_pending),     delta: "—", dir: "flat" },
    { key: "rev",   label: "ערך משוער",     value: fmtValue,                            delta: "—", dir: estValue > 0 ? "up" : "flat" },
    { key: "perf",  label: "בסיכון",        value: String(counts.at_risk),              delta: "—", dir: counts.at_risk > 0 ? "down" : "flat" },
    { key: "rt",    label: "תיאמו",         value: String(booked),                       delta: "—", dir: booked > 0 ? "up" : "flat" },
  ];
}

function buildHeroFromDecision(d: ApiDecision, headlineFallback?: string): HeroRecommendation {
  const why = [d.why_it_matters, d.value_hint]
    .map(s => (s ?? "").trim())
    .filter(Boolean)
    .slice(0, 3);
  return {
    target: d.lead_name?.trim() || d.phone || "—",
    value: TEMP_VALUE_LABEL,
    headline: (d.situation?.trim() || headlineFallback || "החלטה ממתינה").slice(0, 140),
    why: why.length ? why : ["ראה המלצה מצורפת"],
    action: d.recommendation?.trim() || "המתנה לפעולה",
    confidence: confidenceToPct(d.confidence),
    window: "חלון פעולה: עכשיו",
    impact: `+${TEMP_VALUE_LABEL} צפוי`,
  };
}

function buildQuietHero(counts: Required<ApiCounts>, headlineFallback?: string): HeroRecommendation {
  const why: string[] = [`סך לידים פעילים: ${counts.total_leads}`];
  if (counts.at_risk > 0) why.push(`${counts.at_risk} לידים בסיכון`);
  if (counts.booked > 0) why.push(`${counts.booked} פגישות תואמו`);
  if (why.length === 1) why.push("ממתין לפעילות חדשה");
  return {
    target: "מצב מעקב",
    value: "—",
    headline: headlineFallback?.trim() || "מאיה במעקב — אין החלטות פתוחות כרגע",
    why,
    action: "—",
    confidence: 50,
    window: "מצב פעיל",
    impact: "—",
  };
}

function buildOrbitsFromLeads(leads: ApiLead[]): OrbitNode[] {
  const N = clamp(leads.length, 0, 8);
  if (N === 0) return [];
  return leads.slice(0, N).map((l, i) => {
    const theta = (2 * Math.PI * i) / N - Math.PI / 2;
    const r = 0.55 + (i % 3) * 0.13;
    return {
      id: `live:${l.phone ?? i}`,
      name: leadDisplayName(l),
      value: TEMP_VALUE_LABEL,
      r,
      theta,
      state: statusToOrbitState(l.status),
      label: statusLabelHe(l.status),
    };
  });
}

function buildWhatsAppFromLeads(leads: ApiLead[]): WhatsAppThread[] {
  return leads
    .filter(l => l.last_inbound?.body || l.last_outbound?.body)
    .slice(0, 4)
    .map((l, i) => {
      const ib = l.last_inbound;
      const ob = l.last_outbound;
      const inboundNewer =
        ib?.ts && (!ob?.ts || new Date(ib.ts).getTime() > new Date(ob.ts).getTime());
      const lastTs = inboundNewer ? ib?.ts : ob?.ts ?? ib?.ts;
      const preview = (inboundNewer ? ib?.body : ob?.body ?? ib?.body) ?? "";
      return {
        id: `live:${l.phone ?? i}`,
        who: leadDisplayName(l),
        preview: preview.length > 120 ? preview.slice(0, 117) + "…" : preview,
        ago: relativeAgo(lastTs),
        // Maya owns all outbound currently — mark as AI.
        by: "AI",
        unread: !!inboundNewer,
      };
    });
}

function buildAlertsFromBriefing(briefing: ApiBriefing, counts: Required<ApiCounts>): Alert[] {
  const alerts: Alert[] = [];
  for (const d of (briefing.decisions ?? []).slice(0, 3)) {
    if (!d) continue;
    alerts.push({
      id: d.id ?? `decision:${d.phone ?? Math.random()}`,
      severity: statusToSeverity(d.status),
      ago: "עכשיו",
      who: `${d.lead_name ?? d.phone ?? "ליד"} · ${statusLabelHe(d.status)}`,
      body: (d.situation ?? d.why_it_matters ?? "").slice(0, 200),
    });
  }
  if (alerts.length === 0 && counts.at_risk > 0) {
    alerts.push({
      id: "risk-summary",
      severity: "med",
      ago: "—",
      who: `${counts.at_risk} לידים בסיכון`,
      body: "ממתין לטיפול. שקול לפנות אליהם בהקדם.",
    });
  }
  return alerts;
}

function buildLeadStagesFromCounts(counts: Required<ApiCounts>): LeadStage[] {
  const total = Math.max(counts.total_leads, 1);
  return [
    { stage: "חדשים",        n: counts.no_response,            pct: counts.no_response / total },
    { stage: "ממתין למעקב",  n: counts.followup_pending,       pct: counts.followup_pending / total },
    { stage: "חזרו",         n: counts.replied_after_followup, pct: counts.replied_after_followup / total },
    { stage: "תיאמו",        n: counts.booked,                  pct: counts.booked / total },
    { stage: "בסיכון",       n: counts.at_risk,                 pct: counts.at_risk / total },
  ];
}

// ── Quiet live state ──────────────────────────────────────────────────
// Used when the API succeeds but is fully empty. Must not leak any mock
// business activity — only UI scaffolding (user identity, prompt list).

function emptyKpis(): Kpi[] {
  return [
    { key: "calls", label: "סך לידים",        value: "0", delta: "—", dir: "flat" },
    { key: "leads", label: "חזרו אחרי שחזור", value: "0", delta: "—", dir: "flat" },
    { key: "opps",  label: "ממתין למעקב",     value: "0", delta: "—", dir: "flat" },
    { key: "rev",   label: "ערך משוער",       value: "—", delta: "—", dir: "flat" },
    { key: "perf",  label: "בסיכון",          value: "0", delta: "—", dir: "flat" },
    { key: "rt",    label: "תיאמו",            value: "0", delta: "—", dir: "flat" },
  ];
}

function emptyLeadStages(): LeadStage[] {
  return [
    { stage: "חדשים",        n: 0, pct: 0 },
    { stage: "ממתין למעקב",  n: 0, pct: 0 },
    { stage: "חזרו",         n: 0, pct: 0 },
    { stage: "תיאמו",        n: 0, pct: 0 },
    { stage: "בסיכון",       n: 0, pct: 0 },
  ];
}

function quietLiveHero(): HeroRecommendation {
  return {
    target: "מצב מעקב",
    value: "—",
    headline: "מאיה במעקב",
    why: ["אין כרגע לידים בסיכון או החלטות פתוחות."],
    action: "—",
    confidence: 0,
    window: "—",
    impact: "—",
  };
}

function quietLiveState(identity?: AuthIdentity): WatchData {
  return {
    user: resolveLiveIdentity(identity),
    kpis: emptyKpis(),
    hero: quietLiveHero(),
    calls: [],
    whatsapp: [],
    leads: emptyLeadStages(),
    orbits: [],
    alerts: [],
    insights: [],
    wins: [],
    patterns: [],
    agentToday: [],
    prompts: watchMock.prompts,  // UI scaffolding (suggested questions, not business activity)
  };
}

// ── Top-level mapper ──────────────────────────────────────────────────

/**
 * Map live API payloads into the WatchData shape.
 *
 * Rule: when the API responds successfully (any state — full, partial, or
 * empty), this function MUST NOT inject mock business activity. The only
 * mock values that survive are UI scaffolding (user identity, prompt
 * suggestions). Mock fallback for fields like calls/wins/insights would
 * misrepresent fake activity as real client data.
 *
 * - Fully empty (no decisions, no leads, total_leads = 0): returns
 *   `quietLiveState()` — honest "monitoring" screen, all zeros, all
 *   panels empty.
 * - Decisions empty but leads exist: hero degrades to a count-derived
 *   monitoring summary. All other fields are live or empty.
 * - Otherwise: full live mapping.
 *
 * Network failure is handled one layer up in WatchShell (mock fallback
 * acceptable for prototype/dev when the backend is unreachable).
 */
export function mapToWatchData(live: MayaWatchLive, identity?: AuthIdentity): WatchData {
  const counts = safeCounts(live.briefing.counts);
  const decisions = live.briefing.decisions ?? [];
  const leads = live.leads;

  const trulyEmpty =
    decisions.length === 0 && leads.length === 0 && counts.total_leads === 0;
  if (trulyEmpty) return quietLiveState(identity);

  const hero =
    decisions.length > 0
      ? buildHeroFromDecision(decisions[0], live.briefing.headline)
      : buildQuietHero(counts, live.briefing.headline);

  return {
    user: resolveLiveIdentity(identity),                        // real or neutral, never mock
    kpis: buildKpisFromCounts(counts),                          // live
    hero,                                                       // live
    calls: [],                                                  // no live source yet — never mock
    whatsapp: leads.length ? buildWhatsAppFromLeads(leads) : [],
    leads: buildLeadStagesFromCounts(counts),                   // live
    orbits: leads.length ? buildOrbitsFromLeads(leads) : [],
    alerts: buildAlertsFromBriefing(live.briefing, counts),     // live
    insights: [],                                               // no live source yet — never mock
    wins: [],                                                   // no live source yet — never mock
    patterns: [],                                               // no live source yet — never mock
    agentToday: [],                                             // no live source yet — never mock
    prompts: watchMock.prompts,                                 // UI scaffolding
  };
}
