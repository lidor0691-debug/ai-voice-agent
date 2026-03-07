export const dynamic = "force-dynamic";

import { fetchLeads } from "@/lib/api";
import { MOCK_LEADS } from "@/lib/mock-data";
import { LeadsClientPage } from "./LeadsClientPage";

export default async function LeadsPage() {
  let leads = MOCK_LEADS;
  try {
    leads = await fetchLeads();
  } catch {
    // backend unavailable — mock data is used as fallback
  }

  return <LeadsClientPage initialLeads={leads} />;
}
