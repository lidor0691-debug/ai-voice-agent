import { NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { supabase } from "@/lib/supabase";
import { computeLeadsStats } from "@/lib/leads-stats";
import type { SupabaseLead, LeadsApiResponse } from "@/types/lead";

export async function GET(): Promise<NextResponse<LeadsApiResponse | { error: string }>> {
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();
  const ctx = getUserContext(user);

  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const query = supabase
    .from("leads")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(200);
  if (!ctx.isAdmin) query.eq("client_id", ctx.clientId);

  const { data, error } = await query;
  if (error) {
    console.error("[/api/leads] Supabase error:", error.message);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  const leads = (data ?? []) as SupabaseLead[];
  return NextResponse.json({ leads, stats: computeLeadsStats(leads) });
}
