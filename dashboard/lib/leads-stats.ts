import type { SupabaseLead } from "@/types/lead";

export function computeLeadsStats(leads: SupabaseLead[]) {
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  const todayISO = todayStart.toISOString();

  return {
    total: leads.length,
    today: leads.filter((l) => l.created_at >= todayISO).length,
    new: leads.filter((l) => l.status === "new").length,
    contacted: leads.filter((l) => l.status === "contacted").length,
    voice: leads.filter((l) => l.source === "voice").length,
    whatsapp: leads.filter((l) => l.source === "whatsapp").length,
  };
}
