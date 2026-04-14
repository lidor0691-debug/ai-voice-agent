export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { CallLog, AgentConfig } from "@/types/database";
import { CallsClientPage } from "./CallsClientPage";

type CallWithAgent = CallLog & { agents_config: Pick<AgentConfig, "agent_name"> | null };

export default async function CallsPage() {
  const supabase = await createSupabaseServerClient();

  const { data: { user } } = await supabase.auth.getUser();
  const clientId = user?.user_metadata?.client_id as string | undefined;

  if (!clientId) {
    return <CallsClientPage calls={null} error="Not authenticated" />;
  }

  // Get this client's agent IDs
  const { data: agents } = await supabase
    .from("agents_config")
    .select("id")
    .eq("client_id", clientId);

  const agentIds = (agents ?? []).map((a: Pick<AgentConfig, "id">) => a.id);

  if (agentIds.length === 0) {
    return <CallsClientPage calls={[]} error={null} />;
  }

  const { data, error } = await supabase
    .from("call_logs")
    .select("*, agents_config(agent_name)")
    .in("agent_id", agentIds)
    .order("created_at", { ascending: false })
    .limit(100);

  return (
    <CallsClientPage
      calls={data as CallWithAgent[] | null}
      error={error?.message ?? null}
    />
  );
}
