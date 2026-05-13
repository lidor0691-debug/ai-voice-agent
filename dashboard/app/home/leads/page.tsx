import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { HomeShell } from "../_shared/HomeShell";
import { HomeNavRail } from "../_shared/HomeNavRail";
import { resolveHomeIdentity } from "../_shared/identity";
import { LeadsTable, type LeadRow } from "./LeadsTable";

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

          <LeadsTable leads={leads} />
        </div>
      </div>
    </HomeShell>
  );
}

export const metadata = { title: "Maya · Leads" };
