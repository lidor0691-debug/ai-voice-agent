import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { HomeShell } from "../_shared/HomeShell";
import { HomeNavRail } from "../_shared/HomeNavRail";
import { resolveHomeIdentity } from "../_shared/identity";

interface LeadRow {
  id: string;
  created_at: string;
  name: string | null;
  phone: string;
  source: string | null;
  status: string | null;
  appointment_at: string | null;
  last_whatsapp_inbound_at: string | null;
  client_id: string | null;
}

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("he-IL", { dateStyle: "short", timeStyle: "short" });
}

export default async function LeadsPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  const identity = resolveHomeIdentity(user);
  const ctx = getUserContext(user);

  let leads: LeadRow[] = [];
  if (ctx) {
    const query = supabase
      .from("leads")
      .select("id, created_at, name, phone, source, status, appointment_at, last_whatsapp_inbound_at, client_id")
      .neq("source", "browser_voice")
      .not("phone", "is", null)
      .order("created_at", { ascending: false })
      .limit(50);
    if (!ctx.isAdmin) query.eq("client_id", ctx.clientId);
    const { data, error } = await query;
    if (error) {
      console.error("[home/leads] fetch failed:", error.message);
    } else {
      leads = (data ?? []) as LeadRow[];
    }
  }

  return (
    <HomeShell lang="he">
      <HomeNavRail lang="he" active="leads" user={identity} />
      <div className="lg:ps-[200px] min-h-full">
        <div className="max-w-5xl mx-auto px-6 py-8 maya-hebrew">
          <header className="mb-6 flex items-baseline justify-between gap-3">
            <h1 className="text-2xl text-[#0B1714]/90 font-semibold">לידים</h1>
            <span className="text-[12px] text-[#0B1714]/55 tnum">
              {leads.length > 0 ? `${leads.length} מתוך אחרונים` : "—"}
            </span>
          </header>

          {leads.length === 0 ? (
            <div className="maya-card text-center py-16 text-[#0B1714]/55 text-[14px]">
              אין לידים להצגה כרגע
            </div>
          ) : (
            <div className="maya-card overflow-x-auto" style={{ padding: 0 }}>
              <table className="w-full text-[13px] text-right">
                <thead className="text-[11px] uppercase tracking-wider text-[#0B1714]/50 border-b border-[#E6DCCB]/70">
                  <tr>
                    <th className="px-4 py-3 font-medium">שם</th>
                    <th className="px-4 py-3 font-medium">טלפון</th>
                    <th className="px-4 py-3 font-medium">סטטוס</th>
                    <th className="px-4 py-3 font-medium">מקור</th>
                    <th className="px-4 py-3 font-medium">וואטסאפ אחרון</th>
                    <th className="px-4 py-3 font-medium">תיאום</th>
                    <th className="px-4 py-3 font-medium">נוצר</th>
                  </tr>
                </thead>
                <tbody>
                  {leads.map((l, i) => (
                    <tr
                      key={l.id}
                      className={i % 2 === 0 ? "" : "bg-[#0B1714]/[0.025]"}
                    >
                      <td className="px-4 py-3 text-[#0B1714]/90">{l.name?.trim() || "—"}</td>
                      <td className="px-4 py-3">
                        <span dir="ltr" className="tabular-nums [unicode-bidi:isolate] text-[#0B1714]/85">
                          {l.phone}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-[#0B1714]/85">{l.status?.trim() || "—"}</td>
                      <td className="px-4 py-3 text-[#0B1714]/70">{l.source?.trim() || "—"}</td>
                      <td className="px-4 py-3 text-[#0B1714]/70 tnum">{fmtDateTime(l.last_whatsapp_inbound_at)}</td>
                      <td className="px-4 py-3 text-[#0B1714]/70 tnum">{fmtDateTime(l.appointment_at)}</td>
                      <td className="px-4 py-3 text-[#0B1714]/55 tnum">{fmtDateTime(l.created_at)}</td>
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

export const metadata = { title: "Maya · Leads" };
