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

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("he-IL", { dateStyle: "short", timeStyle: "short", timeZone: "Asia/Jerusalem" });
}

/** Tiny markdown-lite renderer: splits on H2 (`## …`) and double newlines.
 *  Safe-by-construction — every chunk is rendered as plain text inside
 *  <p>/<h3> elements, never via dangerouslySetInnerHTML. No new deps. */
function renderSummary(md: string | null): React.ReactNode {
  if (!md) return null;
  const lines = md.split("\n");
  const nodes: React.ReactNode[] = [];
  let para: string[] = [];
  const flushPara = (key: string) => {
    if (para.length === 0) return;
    nodes.push(
      <p key={`p-${key}`} className="text-gray-300 text-[13px] leading-relaxed whitespace-pre-wrap">
        {para.join("\n")}
      </p>,
    );
    para = [];
  };
  lines.forEach((line, i) => {
    if (line.startsWith("## ")) {
      flushPara(`f${i}`);
      nodes.push(
        <h3 key={`h-${i}`} className="text-white text-[13px] font-semibold mt-3 mb-1">
          {line.replace(/^##\s+/, "")}
        </h3>,
      );
    } else if (line.trim() === "") {
      flushPara(`b${i}`);
    } else {
      para.push(line);
    }
  });
  flushPara("end");
  return <div className="space-y-1">{nodes}</div>;
}

/** Compact evidence summary. Never dumps raw JSON. Never shows L1 content. */
function evidenceSummary(ev: unknown): string {
  if (!ev || typeof ev !== "object") return "Evidence attached";
  const e = ev as Record<string, unknown>;
  const parts: string[] = [];
  // L1 — table name + id count, no row content
  if (typeof e.layer === "string" && e.layer === "L1" && typeof e.table === "string") {
    const ids = Array.isArray(e.ids) ? e.ids.length : 0;
    parts.push(`L1 · ${e.table} × ${ids} ids`);
  }
  // L3 — topic + version citations, no body_md
  const l3 = e.l3;
  if (Array.isArray(l3) && l3.length > 0) {
    const topics = l3
      .map(x => {
        if (!x || typeof x !== "object") return null;
        const t = (x as Record<string, unknown>).topic;
        const v = (x as Record<string, unknown>).version;
        if (typeof t !== "string") return null;
        return typeof v === "number" ? `${t} v${v}` : t;
      })
      .filter((s): s is string => !!s);
    if (topics.length > 0) parts.push(`L3 · ${topics.join(", ")}`);
  }
  // L2 placeholder for future — show id count only, never canonical_text
  const l2 = e.l2;
  if (Array.isArray(l2) && l2.length > 0) {
    parts.push(`L2 · vertical_patterns × ${l2.length} ids`);
  }
  return parts.length > 0 ? parts.join("  ·  ") : "Evidence attached";
}

function confidenceLabel(c: number | null): string {
  if (c == null) return "—";
  return `${Math.round(c * 100)}%`;
}

export default async function AdminBriefingsPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  const ctx = getUserContext(user);
  // Defense-in-depth — middleware already enforces this, but we double-check.
  if (!ctx?.isAdmin) redirect("/home/watch");

  const { data: briefingsRaw, error: briefingsErr } = await supabase
    .from("analyst_briefings")
    .select(
      "id, client_id, agent_id, period_start, period_end, generated_at, status, visibility, " +
      "data_volume, volume_warning, summary_md, model_version, created_by, created_at",
    )
    .order("generated_at", { ascending: false })
    .limit(50);
  if (briefingsErr) {
    console.error("[admin/briefings] briefings fetch failed:", briefingsErr.message);
  }
  const briefings = (briefingsRaw ?? []) as unknown as BriefingRow[];

  let findingsByBriefing = new Map<string, FindingRow[]>();
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
    if (findingsErr) {
      console.error("[admin/briefings] findings fetch failed:", findingsErr.message);
    }
    for (const f of (findingsRaw ?? []) as unknown as FindingRow[]) {
      const list = findingsByBriefing.get(f.briefing_id) ?? [];
      list.push(f);
      findingsByBriefing.set(f.briefing_id, list);
    }
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <header className="flex items-baseline justify-between gap-3">
        <h1 className="text-white text-lg font-semibold">Analyst Briefings</h1>
        <span className="text-[11px] text-gray-500 tnum">
          {briefings.length > 0 ? `${briefings.length} briefings` : "—"}
        </span>
      </header>

      {briefings.length === 0 ? (
        <div className="border border-border rounded-lg bg-surface-1 p-8 text-center text-gray-500 text-sm">
          No briefings yet.
        </div>
      ) : (
        <div className="space-y-5">
          {briefings.map(b => (
            <BriefingCard key={b.id} b={b} findings={findingsByBriefing.get(b.id) ?? []} />
          ))}
        </div>
      )}
    </div>
  );
}

function BriefingCard({ b, findings }: { b: BriefingRow; findings: FindingRow[] }) {
  return (
    <article className="border border-border rounded-lg bg-surface-1 overflow-hidden">
      {/* Admin-only banner */}
      <div className="bg-amber-500/10 border-b border-amber-500/30 px-5 py-2 flex items-center justify-between gap-3">
        <span className="text-[11px] text-amber-300 font-medium" dir="rtl">
          תצוגת אדמין בלבד · לא גלוי ללקוח
        </span>
        <span className="text-[10px] text-gray-400 font-mono">
          status: {b.status} · visibility: {b.visibility}
        </span>
      </div>

      {/* Header meta */}
      <div className="px-5 py-4 border-b border-border space-y-1.5">
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-[11px] font-mono">
          <MetaRow label="client_id" value={b.client_id} />
          <MetaRow label="agent_id" value={b.agent_id ?? "—"} />
          <MetaRow label="period" value={`${fmtDateTime(b.period_start)} → ${fmtDateTime(b.period_end)}`} />
          <MetaRow label="generated_at" value={fmtDateTime(b.generated_at)} />
          <MetaRow label="data_volume" value={String(b.data_volume ?? "—")} />
          <MetaRow label="volume_warning" value={b.volume_warning ?? "—"} />
          <MetaRow label="model_version" value={b.model_version ?? "—"} />
          <MetaRow label="created_by" value={b.created_by ?? "—"} />
        </div>
      </div>

      {/* Summary */}
      {b.summary_md && (
        <section className="px-5 py-4 border-b border-border" dir="rtl">
          {renderSummary(b.summary_md)}
        </section>
      )}

      {/* Findings */}
      <section className="px-5 py-4">
        <div className="text-[11px] uppercase tracking-wider text-gray-500 mb-3">
          Findings ({findings.length})
        </div>
        <div className="space-y-3">
          {findings.length === 0 && (
            <div className="text-[12px] text-gray-500">No findings.</div>
          )}
          {findings.map(f => <FindingRowCard key={f.id} f={f} />)}
        </div>
      </section>
    </article>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-gray-500 shrink-0">{label}:</span>
      <span className="text-gray-300 truncate" title={value}>{value}</span>
    </div>
  );
}

function FindingRowCard({ f }: { f: FindingRow }) {
  return (
    <div className="border border-border rounded-md bg-surface-2 px-4 py-3" dir="rtl">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="min-w-0">
          <div className="text-[13px] text-white font-medium">{f.title}</div>
          <div className="text-[10.5px] text-gray-500 mt-0.5 font-mono" dir="ltr">
            {f.finding_type}
            {f.recommendation_target ? ` · → ${f.recommendation_target}` : ""}
          </div>
        </div>
        <div className="text-[10.5px] text-gray-400 shrink-0 font-mono" dir="ltr">
          conf {confidenceLabel(f.confidence)} · n={f.sample_size ?? "—"}
        </div>
      </div>

      <dl className="space-y-1.5 text-[12px] text-gray-300 leading-relaxed">
        <FindingRowDl label="עובדה" value={f.fact} />
        {f.interpretation && <FindingRowDl label="פרשנות" value={f.interpretation} />}
        {f.recommendation && <FindingRowDl label="המלצה" value={f.recommendation} />}
      </dl>

      <div className="mt-2 pt-2 border-t border-border/60 text-[10.5px] text-gray-500 font-mono" dir="ltr">
        evidence: {evidenceSummary(f.evidence)}
      </div>
    </div>
  );
}

function FindingRowDl({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-gray-500 text-[10.5px] uppercase tracking-wider mb-0.5">{label}</dt>
      <dd className="text-gray-200 whitespace-pre-wrap">{value}</dd>
    </div>
  );
}

export const metadata = { title: "Admin · Briefings" };
