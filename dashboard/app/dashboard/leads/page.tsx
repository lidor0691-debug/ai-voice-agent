export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { LeadsClientPage } from "./LeadsClientPage";
import { computeLeadsStats } from "@/lib/leads-stats";
import type { LeadsApiResponse, SupabaseLead } from "@/types/lead";

const EMPTY: LeadsApiResponse = {
  leads: [],
  stats: { total: 0, today: 0, new: 0, contacted: 0, voice: 0, whatsapp: 0 },
};

export default async function LeadsPage() {
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);

  if (!ctx) return <LeadsClientPage data={EMPTY} />;

  let data: LeadsApiResponse = EMPTY;
  try {
    const query = client
      .from("leads")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(200);
    if (!ctx.isAdmin) query.eq("client_id", ctx.clientId);

    const { data: rows, error } = await query;
    if (error) throw error;
    const leads = (rows ?? []) as SupabaseLead[];
    data = { leads, stats: computeLeadsStats(leads) };
  } catch (err) {
    console.error("[LeadsPage] Failed to fetch leads:", err);
  }

  return <LeadsClientPage data={data} />;
}
