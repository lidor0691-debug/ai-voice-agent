export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { LeadsClientPage } from "./LeadsClientPage";
import { computeLeadsStats } from "@/lib/leads-stats";
import type { LeadsApiResponse, SupabaseLead } from "@/types/lead";

const EMPTY: LeadsApiResponse = {
  leads: [],
  stats: { total: 0, today: 0, new: 0, contacted: 0, voice: 0, whatsapp: 0 },
};

export default async function LeadsPage() {
  const supabase = await createSupabaseServerClient();

  const { data: { user } } = await supabase.auth.getUser();
  const clientId = user?.user_metadata?.client_id as string | undefined;

  if (!clientId) {
    return <LeadsClientPage data={EMPTY} />;
  }

  let data: LeadsApiResponse = EMPTY;

  try {
    const { data: rows, error } = await supabase
      .from("leads")
      .select("*")
      .eq("client_id", clientId)
      .order("created_at", { ascending: false })
      .limit(200);

    if (error) throw error;

    const leads = (rows ?? []) as SupabaseLead[];
    data = { leads, stats: computeLeadsStats(leads) };
  } catch (err) {
    console.error("[LeadsPage] Failed to fetch leads:", err);
  }

  return <LeadsClientPage data={data} />;
}
