export const dynamic = "force-dynamic";

import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";

interface BriefingRow {
  id: string;
  client_id: string;
  agent_id: string | null;
  period_start: string;
  period_end: string;
  generated_at: string;
  status: string;
  visibility: string;
  data_volume: number | null;
  volume_warning: string | null;
  summary_md: string | null;
  model_version: string | null;
  created_by: string | null;
  created_at: string;
}

interface FindingRow {
  id: string;
  briefing_id: string;
  finding_type: string;
  title: string;
  fact: string;
  interpretation: string | null;
  recommendation: string | null;
  recommendation_target: string | null;
  confidence: number | null;
  sample_size: number | null;
  evidence: unknown;
  created_at: string;
}

// ── Hebrew product-language mappings ─────────────────────────────────────

const FINDING_TYPE_HE: Record<string, string> = {
  repeated_question_cluster:     "שאלה שחוזרת",
  faq_candidate:                 "מועמד ל-FAQ",
  followup_gap:                  "פער בפולואפ",
  no_show_risk:                  "סיכון אי-הגעה",
  price_or_uncertainty_friction: "חוסר ודאות סביב מחיר",
  warm_dropoff:                  "התעניינות שננטשה",
  maya_prompt_gap:               "פער בהתנהגות מאיה",
};

const TARGET_HE: Record<string, string> = {
  maya_prompt:    "שיפור מאיה",
  business_owner: "פעולה לבעל העסק",
  faq:            "עדכון FAQ",
  flow:           "שיפור תהליך",
};

function findingTypeLabel(t: string): string { return FINDING_TYPE_HE[t] ?? t; }
function targetLabel(t: string | null): string | null { return t ? (TARGET_HE[t] ?? t) : null; }

function confidenceBucket(c: number | null): { label: string; tone: "high" | "mid" | "low" | "unknown" } {
  if (c == null) return { label: "—", tone: "unknown" };
  if (c >= 0.7)  return { label: "בינונית-גבוהה", tone: "high" };
  if (c >= 0.5)  return { label: "בינונית",       tone: "mid" };
  return            { label: "נמוכה",           tone: "low" };
}

// ── Date / summary helpers ───────────────────────────────────────────────

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("he-IL", { dateStyle: "short", timeStyle: "short", timeZone: "Asia/Jerusalem" });
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("he-IL", { dateStyle: "short", timeZone: "Asia/Jerusalem" });
}

/** Tiny markdown-lite renderer: H2 headings + paragraphs, plain text only. */
function renderSummary(md: string | null): React.ReactNode {
  if (!md) return null;
  const lines = md.split("\n");
  const nodes: React.ReactNode[] = [];
  let para: string[] = [];
  const flush = (k: string) => {
    if (para.length === 0) return;
    nodes.push(
      <p key={`p-${k}`} className="text-gray-200 text-[14px] leading-relaxed whitespace-pre-wrap">
        {para.join("\n")}
      </p>,
    );
    para = [];
  };
  lines.forEach((line, i) => {
    if (line.startsWith("## ")) {
      flush(`f${i}`);
      nodes.push(
        <h3 key={`h-${i}`} className="text-white text-[15px] font-semibold mt-3 mb-1.5">
          {line.replace(/^##\s+/, "")}
        </h3>,
      );
    } else if (line.trim() === "") flush(`b${i}`);
    else para.push(line);
  });
  flush("end");
  return <div className="space-y-1">{nodes}</div>;
}

// ── Evidence summary: produce human bullets, never raw JSON ──────────────

interface EvidenceSummary {
  bullets: string[];        // friendly Hebrew sentences for clients
  techDetail: string;       // muted line for admin-only "פרטים טכניים"
}

function evidenceSummary(ev: unknown): EvidenceSummary {
  const empty: EvidenceSummary = { bullets: [], techDetail: "—" };
  if (!ev || typeof ev !== "object") return empty;
  const e = ev as Record<string, unknown>;

  const bullets: string[] = [];
  const tech: string[] = [];

  // L1 — id count → friendly noun
  if (typeof e.layer === "string" && e.layer === "L1" && typeof e.table === "string") {
    const ids = Array.isArray(e.ids) ? e.ids.length : 0;
    if (ids > 0) {
      const noun = e.table === "leads" ? "לידים" : "תובנות";
      bullets.push(`מבוסס על ${ids} ${noun} מהדאטה של העסק`);
    }
    tech.push(`L1 · ${e.table} × ${ids}`);
  }

  // L3 — playbook citation
  const l3 = e.l3;
  if (Array.isArray(l3) && l3.length > 0) {
    bullets.push("כולל עיקרון מקצועי מתוך ספר המשחקים של מאיה");
    const topics = l3
      .map(x => {
        if (!x || typeof x !== "object") return null;
        const t = (x as Record<string, unknown>).topic;
        const v = (x as Record<string, unknown>).version;
        if (typeof t !== "string") return null;
        return typeof v === "number" ? `${t} v${v}` : t;
      })
      .filter((s): s is string => !!s);
    if (topics.length > 0) tech.push(`L3 · ${topics.join(", ")}`);
  }

  // L2 — future: vertical patterns
  const l2 = e.l2;
  if (Array.isArray(l2) && l2.length > 0) {
    bullets.push("כולל דפוס מצרפי מהענף");
    tech.push(`L2 × ${l2.length}`);
  }

  if (bullets.length === 0) bullets.push("מבוסס על דאטה פנימית");
  return { bullets, techDetail: tech.length > 0 ? tech.join("  ·  ") : "—" };
}

// ── Page ─────────────────────────────────────────────────────────────────

export default async function AdminBriefingsPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  const ctx = getUserContext(user);
  if (!ctx?.isAdmin) redirect("/home/watch");

  const { data: briefingsRaw, error: briefingsErr } = await supabase
    .from("analyst_briefings")
    .select(
      "id, client_id, agent_id, period_start, period_end, generated_at, status, visibility, " +
      "data_volume, volume_warning, summary_md, model_version, created_by, created_at",
    )
    .order("generated_at", { ascending: false })
    .limit(50);
  if (briefingsErr) console.error("[admin/briefings] briefings fetch failed:", briefingsErr.message);
  const briefings = (briefingsRaw ?? []) as unknown as BriefingRow[];

  const findingsByBriefing = new Map<string, FindingRow[]>();
  if (briefings.length > 0) {
    const ids = briefings.map(b => b.id);
    const { data: findingsRaw, error: findingsErr } = await supabase
      .from("analyst_briefing_findings")
      .select(
        "id, briefing_id, finding_type, title, fact, interpretation, recommendation, " +
        "recommendation_target, confidence, sample_size, evidence, created_at",
      )
      .in("briefing_id", ids)
      .order("created_at", { ascending: true });
    if (findingsErr) console.error("[admin/briefings] findings fetch failed:", findingsErr.message);
    for (const f of (findingsRaw ?? []) as unknown as FindingRow[]) {
      const list = findingsByBriefing.get(f.briefing_id) ?? [];
      list.push(f);
      findingsByBriefing.set(f.briefing_id, list);
    }
  }

  return (
    <div className="space-y-7 max-w-4xl">
      <header className="flex items-baseline justify-between gap-3" dir="rtl">
        <h1 className="text-white text-xl font-semibold">תובנות מאיה</h1>
        <span className="text-[11px] text-gray-500 tnum" dir="ltr">
          {briefings.length > 0 ? `${briefings.length} briefings` : "—"}
        </span>
      </header>

      {briefings.length === 0 ? (
        <div className="border border-border rounded-lg bg-surface-1 p-10 text-center text-gray-500 text-sm">
          אין עדיין בריפינגים להצגה.
        </div>
      ) : (
        <div className="space-y-8">
          {briefings.map(b => (
            <BriefingCard key={b.id} b={b} findings={findingsByBriefing.get(b.id) ?? []} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Briefing card ────────────────────────────────────────────────────────

function BriefingCard({ b, findings }: { b: BriefingRow; findings: FindingRow[] }) {
  const lowData = b.volume_warning === "low_data";
  const periodLabel = `${fmtDate(b.period_start)} → ${fmtDate(b.period_end)}`;

  return (
    <article className="border border-border rounded-xl bg-surface-1 overflow-hidden shadow-[0_2px_20px_-10px_rgba(0,0,0,0.4)]">
      {/* Admin-only banner — preserved */}
      <div className="bg-amber-500/10 border-b border-amber-500/30 px-6 py-2 flex items-center justify-between gap-3">
        <span className="text-[11px] text-amber-300 font-medium" dir="rtl">
          תצוגת אדמין בלבד · לא גלוי ללקוח
        </span>
        <span className="text-[10px] text-gray-500 font-mono" dir="ltr">
          {b.status} · {b.visibility}
        </span>
      </div>

      {/* Summary hero */}
      <section className="px-6 py-6 border-b border-border" dir="rtl">
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <h2 className="text-white text-[18px] font-semibold">תקציר מנהל</h2>
          <span className="text-[11px] text-gray-500 tnum" dir="ltr">{periodLabel}</span>
          {lowData && <LowDataBadge />}
        </div>
        {b.summary_md && renderSummary(b.summary_md)}
      </section>

      {/* Findings */}
      <section className="px-6 py-6 border-b border-border" dir="rtl">
        <div className="flex items-baseline gap-3 mb-5">
          <h2 className="text-white text-[16px] font-semibold">תובנות מרכזיות</h2>
          <span className="text-[11px] text-gray-500 tnum">{findings.length}</span>
        </div>
        <div className="space-y-5">
          {findings.length === 0 && (
            <div className="text-[12px] text-gray-500">אין תובנות בבריפינג זה.</div>
          )}
          {findings.map(f => <FindingCard key={f.id} f={f} />)}
        </div>
      </section>

      {/* Tech details footer — admin-only context, kept muted */}
      <details className="px-6 py-3 text-[11px] text-gray-500 group">
        <summary className="cursor-pointer select-none hover:text-gray-300 transition-colors" dir="rtl">
          פרטים טכניים
        </summary>
        <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 font-mono text-[10.5px] text-gray-500" dir="ltr">
          <TechRow label="client_id" value={b.client_id} />
          <TechRow label="agent_id" value={b.agent_id ?? "—"} />
          <TechRow label="period" value={`${fmtDateTime(b.period_start)} → ${fmtDateTime(b.period_end)}`} />
          <TechRow label="generated_at" value={fmtDateTime(b.generated_at)} />
          <TechRow label="data_volume" value={String(b.data_volume ?? "—")} />
          <TechRow label="volume_warning" value={b.volume_warning ?? "—"} />
          <TechRow label="model_version" value={b.model_version ?? "—"} />
          <TechRow label="created_by" value={b.created_by ?? "—"} />
        </div>
      </details>
    </article>
  );
}

function LowDataBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 text-[10.5px] text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-full px-2 py-0.5">
      <span className="w-1 h-1 rounded-full bg-amber-300" />
      אזהרת דאטה נמוך
    </span>
  );
}

function TechRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2 min-w-0">
      <span className="text-gray-600 shrink-0">{label}:</span>
      <span className="text-gray-400 truncate" title={value}>{value}</span>
    </div>
  );
}

// ── Finding card ─────────────────────────────────────────────────────────

function FindingCard({ f }: { f: FindingRow }) {
  const ev = evidenceSummary(f.evidence);
  const confBucket = confidenceBucket(f.confidence);
  const target = targetLabel(f.recommendation_target);

  return (
    <div className="border border-border rounded-lg bg-surface-2 px-5 py-4" dir="rtl">
      {/* Title + pills */}
      <h3 className="text-white text-[15px] font-medium leading-snug mb-2">{f.title}</h3>
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <Pill kind="type">{findingTypeLabel(f.finding_type)}</Pill>
        {target && <Pill kind="target">{target}</Pill>}
        <ConfidencePill bucket={confBucket} />
      </div>

      {/* Body sections */}
      <Section label="מה מאיה ראתה">{f.fact}</Section>
      {f.interpretation && <Section label="מה זה אומר">{f.interpretation}</Section>}
      {f.recommendation && <Section label="מה מומלץ לעשות">{f.recommendation}</Section>}

      {/* Evidence — friendly bullets */}
      <div className="mt-4 pt-3 border-t border-border/60">
        <div className="text-[11px] uppercase tracking-wider text-gray-500 mb-2">על מה זה מבוסס</div>
        <ul className="space-y-1">
          {ev.bullets.map((b, i) => (
            <li key={i} className="text-[12.5px] text-gray-300 flex items-start gap-2">
              <span className="text-gray-600 mt-1 shrink-0">•</span>
              <span>{b}</span>
            </li>
          ))}
        </ul>
        {/* Tech detail for admin only — collapsed and muted */}
        <details className="mt-2 group">
          <summary className="cursor-pointer select-none text-[10.5px] text-gray-600 hover:text-gray-400 transition-colors" dir="rtl">
            פרטים טכניים
          </summary>
          <div className="mt-1.5 text-[10.5px] text-gray-500 font-mono flex flex-wrap gap-x-3 gap-y-1" dir="ltr">
            <span>type: {f.finding_type}</span>
            <span>target: {f.recommendation_target ?? "—"}</span>
            <span>conf: {f.confidence != null ? f.confidence.toFixed(2) : "—"}</span>
            <span>n: {f.sample_size ?? "—"}</span>
            <span>evidence: {ev.techDetail}</span>
          </div>
        </details>
      </div>
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mt-2.5">
      <div className="text-[11px] uppercase tracking-wider text-gray-500 mb-1">{label}</div>
      <div className="text-[13.5px] text-gray-200 leading-relaxed whitespace-pre-wrap">{children}</div>
    </div>
  );
}

// ── Pills ────────────────────────────────────────────────────────────────

function Pill({ kind, children }: { kind: "type" | "target"; children: React.ReactNode }) {
  const tone = kind === "type"
    ? "text-brand-300 bg-brand-600/15 border-brand-600/30"
    : "text-gray-300 bg-gray-500/10 border-gray-500/30";
  return (
    <span className={`text-[11px] px-2 py-0.5 rounded-full border ${tone}`}>
      {children}
    </span>
  );
}

function ConfidencePill({ bucket }: { bucket: { label: string; tone: "high" | "mid" | "low" | "unknown" } }) {
  const tone =
    bucket.tone === "high" ? "text-emerald-300 bg-emerald-500/10 border-emerald-500/30" :
    bucket.tone === "mid"  ? "text-sky-300 bg-sky-500/10 border-sky-500/30" :
    bucket.tone === "low"  ? "text-gray-400 bg-gray-500/10 border-gray-500/30" :
                              "text-gray-500 bg-gray-500/10 border-gray-500/30";
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11px] px-2 py-0.5 rounded-full border ${tone}`}>
      <span className="text-[10px] uppercase tracking-wider opacity-70">רמת ביטחון</span>
      <span className="font-medium">{bucket.label}</span>
    </span>
  );
}

export const metadata = { title: "Admin · Briefings" };
