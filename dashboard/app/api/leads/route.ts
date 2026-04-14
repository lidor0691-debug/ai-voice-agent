import { NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { computeLeadsStats } from "@/lib/leads-stats";
import type { SupabaseLead, LeadsApiResponse } from "@/types/lead";

export async function GET(): Promise<NextResponse<LeadsApiResponse | { error: string }>> {
  const supabase = await createSupabaseServerClient();

  const { data: { user } } = await supabase.auth.getUser();
  const clientId = user?.user_metadata?.client_id as string | undefined;

  if (!clientId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { data, error } = await supabase
    .from("leads")
    .select("*")
    .eq("client_id", clientId)
    .order("created_at", { ascending: false })
    .limit(200);

  if (error) {
    console.error("[/api/leads] Supabase error:", error.message);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  const leads = (data ?? []) as SupabaseLead[];
  return NextResponse.json({ leads, stats: computeLeadsStats(leads) });
}
