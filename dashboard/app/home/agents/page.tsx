import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { HomeShell } from "../_shared/HomeShell";
import { HomeNavRail } from "../_shared/HomeNavRail";
import { resolveHomeIdentity } from "../_shared/identity";

interface AgentRow {
  id: string;
  agent_name: string | null;
  business_name: string | null;
  is_active: boolean | null;
  phone_number: string | null;
  whatsapp_number: string | null;
  whatsapp_enabled: boolean | null;
  whatsapp_followup_enabled: boolean | null;
  language: string | null;
  tone: string | null;
  lead_delivery_method: string | null;
  updated_at: string | null;
  created_at: string | null;
  client_id: string | null;
}

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("he-IL", { dateStyle: "short", timeStyle: "short", timeZone: "Asia/Jerusalem" });
}

export default async function AgentsPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  const identity = resolveHomeIdentity(user);
  const ctx = getUserContext(user);

  let agents: AgentRow[] = [];
  if (ctx) {
    const query = supabase
      .from("agents_config")
      .select(
        "id, agent_name, business_name, is_active, phone_number, whatsapp_number, whatsapp_enabled, whatsapp_followup_enabled, language, tone, lead_delivery_method, updated_at, created_at, client_id",
      )
      .order("is_active", { ascending: false })
      .order("updated_at", { ascending: false })
      .limit(50);
    if (!ctx.isAdmin) query.eq("client_id", ctx.clientId);

    const { data, error } = await query;
    if (error) {
      console.error("[home/agents] fetch failed:", error.message);
    } else {
      agents = (data ?? []) as AgentRow[];
    }
  }

  return (
    <HomeShell lang="he">
      <HomeNavRail lang="he" active="agents" user={identity} />
      <div className="lg:ps-[200px] min-h-full">
        <div className="max-w-3xl mx-auto px-6 py-8 maya-hebrew">
          <header className="mb-6 flex items-baseline justify-between gap-3">
            <h1 className="text-2xl text-[#0B1714]/90 font-semibold">סוכנים</h1>
            <span className="text-[12px] text-[#0B1714]/55 tnum">
              {agents.length > 0 ? `${agents.length} מתוך אחרונים` : "—"}
            </span>
          </header>

          {agents.length === 0 ? (
            <div className="maya-card text-center py-16 text-[#0B1714]/55 text-[14px]">
              אין סוכנים להצגה כרגע
            </div>
          ) : (
            <div className="space-y-4">
              {agents.map(a => <AgentCard key={a.id} a={a} />)}
            </div>
          )}
        </div>
      </div>
    </HomeShell>
  );
}

function AgentCard({ a }: { a: AgentRow }) {
  const active = !!a.is_active;
  const muted = !active;
  const name = a.agent_name?.trim() || "—";
  const biz = a.business_name?.trim() || "";

  return (
    <div className={`maya-card ${muted ? "opacity-70" : ""}`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <div className="text-[16px] text-[#0B1714]/90 font-semibold truncate">{name}</div>
          {biz && (
            <div className="text-[12px] text-[#0B1714]/55 mt-0.5 truncate">{biz}</div>
          )}
        </div>
        <StatusPill active={active} />
      </div>

      {/* Channels */}
      <div className="space-y-1.5 text-[13px] text-[#0B1714]/85">
        <ChannelLine label="מספר קולי" phone={a.phone_number} />
        {a.whatsapp_number && (
          <ChannelLine
            label="וואטסאפ"
            phone={a.whatsapp_number}
            extras={[
              a.whatsapp_enabled ? "פעיל" : "מושבת",
              a.whatsapp_followup_enabled ? "שחזור פעיל" : null,
            ].filter(Boolean) as string[]}
          />
        )}
      </div>

      {/* Personality + routing */}
      <div className="mt-3 pt-3 border-t border-[#E6DCCB]/70 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11.5px] text-[#0B1714]/70">
        <Chip label="שפה" value={a.language} />
        <Chip label="טון" value={a.tone} />
        <Chip label="ניתוב לידים" value={a.lead_delivery_method} />
      </div>

      {/* Footer */}
      <div className="mt-3 pt-2 border-t border-[#E6DCCB]/40 text-[10.5px] text-[#0B1714]/45 tnum">
        עודכן: {fmtDateTime(a.updated_at)}
      </div>
    </div>
  );
}

function StatusPill({ active }: { active: boolean }) {
  if (active) {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] text-[#0B1714]/80 shrink-0">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
        פעיל
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-[#0B1714]/55 shrink-0">
      <span className="w-1.5 h-1.5 rounded-full bg-[#0B1714]/30" />
      לא פעיל
    </span>
  );
}

function ChannelLine({ label, phone, extras }: { label: string; phone: string | null; extras?: string[] }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-[#0B1714]/55 shrink-0">{label}:</span>
      <span dir="ltr" className="tabular-nums [unicode-bidi:isolate]">
        {phone?.trim() || "—"}
      </span>
      {extras && extras.length > 0 && (
        <>
          <span className="text-[#0B1714]/30">·</span>
          <span className="text-[#0B1714]/65 text-[12px]">{extras.join(" · ")}</span>
        </>
      )}
    </div>
  );
}

function Chip({ label, value }: { label: string; value: string | null }) {
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span className="text-[#0B1714]/45 uppercase tracking-wider">{label}</span>
      <span className="text-[#0B1714]/85">{value?.trim() || "—"}</span>
    </span>
  );
}

export const metadata = { title: "Maya · Agents" };
