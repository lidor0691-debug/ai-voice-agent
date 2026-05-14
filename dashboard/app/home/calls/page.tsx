import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { HomeShell } from "../_shared/HomeShell";
import { HomeNavRail } from "../_shared/HomeNavRail";
import { resolveHomeIdentity } from "../_shared/identity";

interface CallRow {
  id: string;
  agent_id: string | null;
  phone_number: string | null;
  status: string | null;
  duration: number | null;
  created_at: string;
  agents_config:
    | { agent_name: string | null }
    | { agent_name: string | null }[]
    | null;
}

function agentNameOf(row: CallRow): string {
  const a = row.agents_config;
  if (!a) return "—";
  const flat = Array.isArray(a) ? a[0] : a;
  return flat?.agent_name?.trim() || "—";
}

function fmtDuration(seconds: number | null): string {
  if (seconds == null || seconds <= 0) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("he-IL", { dateStyle: "short", timeStyle: "short", timeZone: "Asia/Jerusalem" });
}

export default async function CallsPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  const identity = resolveHomeIdentity(user);
  const ctx = getUserContext(user);

  let calls: CallRow[] = [];

  if (ctx) {
    if (ctx.isAdmin) {
      const { data, error } = await supabase
        .from("call_logs")
        .select("id, agent_id, phone_number, status, duration, created_at, agents_config(agent_name)")
        .order("created_at", { ascending: false })
        .limit(50);
      if (error) {
        console.error("[home/calls] fetch failed:", error.message);
      } else {
        calls = (data ?? []) as CallRow[];
      }
    } else {
      const { data: agents, error: agentsErr } = await supabase
        .from("agents_config")
        .select("id")
        .eq("client_id", ctx.clientId);
      if (agentsErr) {
        console.error("[home/calls] agents_config lookup failed:", agentsErr.message);
      }
      const agentIds = (agents ?? []).map(a => a.id as string).filter(Boolean);
      if (agentIds.length > 0) {
        const { data, error } = await supabase
          .from("call_logs")
          .select("id, agent_id, phone_number, status, duration, created_at, agents_config(agent_name)")
          .in("agent_id", agentIds)
          .order("created_at", { ascending: false })
          .limit(50);
        if (error) {
          console.error("[home/calls] fetch failed:", error.message);
        } else {
          calls = (data ?? []) as CallRow[];
        }
      }
    }
  }

  return (
    <HomeShell lang="he">
      <HomeNavRail lang="he" active="calls" user={identity} />
      <div className="lg:ps-[200px] min-h-full">
        <div className="max-w-5xl mx-auto px-6 py-8 maya-hebrew">
          <header className="mb-6 flex items-baseline justify-between gap-3">
            <h1 className="text-2xl text-[#0B1714]/90 font-semibold">שיחות</h1>
            <span className="text-[12px] text-[#0B1714]/55 tnum">
              {calls.length > 0 ? `${calls.length} מתוך אחרונים` : "—"}
            </span>
          </header>

          {calls.length === 0 ? (
            <div className="maya-card text-center py-16 text-[#0B1714]/55 text-[14px]">
              אין שיחות להצגה כרגע
            </div>
          ) : (
            <div className="maya-card overflow-x-auto" style={{ padding: 0 }}>
              <table className="w-full text-[13px] text-right">
                <thead className="text-[11px] uppercase tracking-wider text-[#0B1714]/50 border-b border-[#E6DCCB]/70">
                  <tr>
                    <th className="px-4 py-3 font-medium">טלפון</th>
                    <th className="px-4 py-3 font-medium">סטטוס</th>
                    <th className="px-4 py-3 font-medium">סוכן</th>
                    <th className="px-4 py-3 font-medium">משך</th>
                    <th className="px-4 py-3 font-medium">מועד</th>
                  </tr>
                </thead>
                <tbody>
                  {calls.map((c, i) => (
                    <tr key={c.id} className={i % 2 === 0 ? "" : "bg-[#0B1714]/[0.025]"}>
                      <td className="px-4 py-3">
                        <span dir="ltr" className="tabular-nums [unicode-bidi:isolate] text-[#0B1714]/85">
                          {c.phone_number?.trim() || "—"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-[#0B1714]/85">{c.status?.trim() || "—"}</td>
                      <td className="px-4 py-3 text-[#0B1714]/70">{agentNameOf(c)}</td>
                      <td className="px-4 py-3 text-[#0B1714]/70 tnum">{fmtDuration(c.duration)}</td>
                      <td className="px-4 py-3 text-[#0B1714]/55 tnum">{fmtDateTime(c.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </HomeShell>
  );
}

export const metadata = { title: "Maya · Calls" };
