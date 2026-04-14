import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import type { SupabaseLead, LeadsApiResponse } from "@/types/lead";

export async function GET(): Promise<NextResponse<LeadsApiResponse | { error: string }>> {
  const { data, error } = await supabase
    .from("leads")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(200);

  if (error) {
    console.error("[/api/leads] Supabase error:", error.message);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  const leads = (data ?? []) as SupabaseLead[];

  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  const todayISO = todayStart.toISOString();

  const stats = {
    total: leads.length,
    today: leads.filter((l) => l.created_at >= todayISO).length,
    new: leads.filter((l) => l.status === "new").length,
    contacted: leads.filter((l) => l.status === "contacted").length,
    voice: leads.filter((l) => l.source === "voice").length,
    whatsapp: leads.filter((l) => l.source === "whatsapp").length,
  };

  return NextResponse.json({ leads, stats });
}
