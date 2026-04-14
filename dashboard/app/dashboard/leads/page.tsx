export const dynamic = "force-dynamic";

import { LeadsClientPage } from "./LeadsClientPage";
import type { LeadsApiResponse } from "@/types/lead";

const EMPTY: LeadsApiResponse = {
  leads: [],
  stats: { total: 0, today: 0, new: 0, contacted: 0, voice: 0, whatsapp: 0 },
};

export default async function LeadsPage() {
  let data: LeadsApiResponse = EMPTY;

  try {
    const { supabase } = await import("@/lib/supabase");

    const { data: rows, error } = await supabase
      .from("leads")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(200);

    if (error) throw error;

    const leads = rows ?? [];
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);
    const todayISO = todayStart.toISOString();

    data = {
      leads,
      stats: {
        total: leads.length,
        today: leads.filter((l: { created_at: string }) => l.created_at >= todayISO).length,
        new: leads.filter((l: { status: string }) => l.status === "new").length,
        contacted: leads.filter((l: { status: string }) => l.status === "contacted").length,
        voice: leads.filter((l: { source: string }) => l.source === "voice").length,
        whatsapp: leads.filter((l: { source: string }) => l.source === "whatsapp").length,
      },
    };
  } catch (err) {
    console.error("[LeadsPage] Failed to fetch leads:", err);
  }

  return <LeadsClientPage data={data} />;
}
