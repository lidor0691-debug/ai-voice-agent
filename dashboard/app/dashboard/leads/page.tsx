export const dynamic = "force-dynamic";

import { fetchLeadsFromSheets, fetchLeads } from "@/lib/api";
import { MOCK_LEADS } from "@/lib/mock-data";
import { LeadsClientPage } from "./LeadsClientPage";

export default async function LeadsPage() {
  // Priority: Google Sheets → FastAPI backend → mock data
  let leads = MOCK_LEADS;
  try {
    leads = await fetchLeadsFromSheets();
  } catch {
    try {
      leads = await fetchLeads();
    } catch {
      // all sources unavailable — use mock data
    }
  }

  return <LeadsClientPage initialLeads={leads} />;
}
