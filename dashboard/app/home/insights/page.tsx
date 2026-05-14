import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { createSupabaseAdminClient } from "@/lib/supabase-admin";
import { getUserContext } from "@/lib/user-context";
import { HomeShell } from "../_shared/HomeShell";
import { HomeNavRail } from "../_shared/HomeNavRail";
import { resolveHomeIdentity } from "../_shared/identity";

interface InsightRow {
  id: string;
  insight_type: string | null;
  title: string | null;
  normalized_text: string | null;
  frequency_count: number | null;
  status: string | null;
  source_type: string | null;
  intent_category: string | null;
  created_at: string | null;
  updated_at: string | null;
  client_id: string | null;
}

const INSIGHT_TYPE_HE: Record<string, string> = {
  question: "שאלות נפוצות",
  intent_signal: "סימני כוונה",
  objection: "התנגדויות",
  topic: "נושאים חמים",
  faq_candidate: "מועמד ל־FAQ",
  content_opportunity: "הזדמנויות תוכן",
};

const SOURCE_HE: Record<string, string> = {
  whatsapp: "ווטסאפ",
  voice: "קולי",
  call: "קולי",
  chat: "צ׳אט",
};

const TYPE_ORDER = [
  "question",
  "intent_signal",
  "objection",
  "topic",
  "faq_candidate",
  "content_opportunity",
];

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("he-IL", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Asia/Jerusalem",
  });
}

function insightTypeLabel(t: string | null): string {
  if (!t) return "—";
  return INSIGHT_TYPE_HE[t] ?? t;
}

function sourceLabel(s: string | null): string {
  if (!s) return "—";
  return SOURCE_HE[s] ?? s;
}

function normalize(s: string | null | undefined): string {
  return (s ?? "").trim().toLowerCase();
}

export default async function InsightsPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  const identity = resolveHomeIdentity(user);
  const ctx = getUserContext(user);

  let insights: InsightRow[] = [];
  if (ctx) {
    // TODO(security): Replace this admin-client read with proper RLS SELECT
    // policies for lead_intelligence_insights once RLS/auth hardening is
    // handled. Today the table has RLS enabled but zero policies, so the
    // user-scoped client returns 0 rows. We mirror the same approved
    // server-side admin-client + code-side client_id scoping pattern used
    // by /api/whatsapp-history and the /home/leads Maya Watch merge.
    const admin = createSupabaseAdminClient();
    const query = admin
      .from("lead_intelligence_insights")
      .select(
        "id, insight_type, title, normalized_text, frequency_count, status, source_type, intent_category, created_at, updated_at, client_id",
      )
      .order("frequency_count", { ascending: false })
      .order("created_at", { ascending: false })
      .limit(100);
    if (!ctx.isAdmin) query.eq("client_id", ctx.clientId);

    const { data, error } = await query;
    if (error) {
      console.error("[home/insights] fetch failed:", error.message);
    } else {
      const rows = (data ?? []) as InsightRow[];
      // Defense-in-depth: re-enforce tenant scope in code for non-admins,
      // since we bypassed RLS via the admin client.
      insights = ctx.isAdmin
        ? rows
        : rows.filter(r => r.client_id === ctx.clientId);
    }
  }

  // Group by insight_type while preserving server-side sort order within each bucket.
  const groups = new Map<string, InsightRow[]>();
  for (const row of insights) {
    const key = row.insight_type ?? "—";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(row);
  }

  // Section order: known types in TYPE_ORDER first, then any unknown types,
  // each preserved at first-appearance order.
  const orderedKeys: string[] = [];
  for (const k of TYPE_ORDER) {
    if (groups.has(k)) orderedKeys.push(k);
  }
  for (const k of groups.keys()) {
    if (!orderedKeys.includes(k)) orderedKeys.push(k);
  }

  return (
    <HomeShell lang="he">
      <HomeNavRail lang="he" active="insights" user={identity} />
      <div className="lg:ps-[200px] min-h-full">
        <div className="max-w-3xl mx-auto px-6 py-8 maya-hebrew">
          <header className="mb-6 flex items-baseline justify-between gap-3">
            <h1 className="text-2xl text-[#0B1714]/90 font-semibold">תובנות</h1>
            <span className="text-[12px] text-[#0B1714]/55 tnum">
              {insights.length > 0 ? `${insights.length} מתוך אחרונות` : "—"}
            </span>
          </header>

          {insights.length === 0 ? (
            <div className="maya-card text-center py-16 text-[#0B1714]/55 text-[14px]">
              אין תובנות להצגה כרגע
            </div>
          ) : (
            <div className="space-y-6">
              {orderedKeys.map(key => (
                <InsightSection key={key} typeKey={key} rows={groups.get(key) ?? []} />
              ))}
            </div>
          )}
        </div>
      </div>
    </HomeShell>
  );
}

function InsightSection({ typeKey, rows }: { typeKey: string; rows: InsightRow[] }) {
  return (
    <section className="maya-card">
      <header className="flex items-baseline justify-between gap-3 mb-3">
        <h2 className="text-[15px] text-[#0B1714]/90 font-semibold">
          {insightTypeLabel(typeKey)}
        </h2>
        <span className="text-[11px] text-[#0B1714]/55 tnum">{rows.length}</span>
      </header>
      <ul className="divide-y divide-[#E6DCCB]/70">
        {rows.map(r => <InsightItem key={r.id} r={r} />)}
      </ul>
    </section>
  );
}

function InsightItem({ r }: { r: InsightRow }) {
  const title = r.title?.trim() || "—";
  const sub = r.normalized_text?.trim() || "";
  const showSub = sub && normalize(sub) !== normalize(title);
  const freq = r.frequency_count ?? 0;

  return (
    <li className="py-3 first:pt-0 last:pb-0">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-[13.5px] text-[#0B1714]/90 leading-snug">{title}</div>
          {showSub && (
            <div className="text-[12px] text-[#0B1714]/55 leading-snug mt-1 line-clamp-2">
              {sub}
            </div>
          )}
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px] text-[#0B1714]/55">
            <span>{sourceLabel(r.source_type)}</span>
            {r.intent_category?.trim() && (
              <>
                <span className="text-[#0B1714]/25">·</span>
                <span>{r.intent_category.trim()}</span>
              </>
            )}
            <span className="text-[#0B1714]/25">·</span>
            <span className="tnum">{fmtDate(r.created_at)}</span>
          </div>
        </div>
        {freq > 0 && (
          <span className="text-[11px] text-[#0B1714]/85 tnum shrink-0 px-2 py-0.5 rounded-full bg-[#0B1714]/[0.06]">
            ×{freq}
          </span>
        )}
      </div>
    </li>
  );
}

export const metadata = { title: "Maya · Insights" };
