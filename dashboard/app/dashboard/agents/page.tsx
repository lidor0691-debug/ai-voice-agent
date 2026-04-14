export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { AgentConfig } from "@/types/database";
import { AgentsClientPage } from "./AgentsClientPage";

export default async function AgentsPage() {
  const supabase = await createSupabaseServerClient();

  const { data: { user } } = await supabase.auth.getUser();
  const clientId = user?.user_metadata?.client_id as string | undefined;

  if (!clientId) {
    return <AgentsClientPage agents={null} error="Not authenticated" />;
  }

  const { data, error } = await supabase
    .from("agents_config")
    .select("*")
    .eq("client_id", clientId)
    .order("created_at", { ascending: false });

  return (
    <AgentsClientPage
      agents={data as AgentConfig[] | null}
      error={error?.message ?? null}
    />
  );
}
