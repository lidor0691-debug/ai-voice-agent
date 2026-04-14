export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { AgentConfig, CallLog } from "@/types/database";
import { DashboardClientPage } from "./DashboardClientPage";

export default async function DashboardPage() {
  const supabase = await createSupabaseServerClient();

  const { data: { user } } = await supabase.auth.getUser();
  const clientId = user?.user_metadata?.client_id as string | undefined;

  if (!clientId) {
    return (
      <DashboardClientPage agents={null} calls={null} knowledgeCount={0} />
    );
  }

  // Fetch agents filtered by client
  const agentRes = await supabase
    .from("agents_config")
    .select("id, agent_name, is_active, system_prompt, first_message, phone_number")
    .eq("client_id", clientId)
    .order("created_at", { ascending: false });

  // Fetch client's agent IDs to filter calls
  const agentIds = (agentRes.data ?? []).map(
    (a: Pick<AgentConfig, "id">) => a.id
  );

  const callRes = agentIds.length > 0
    ? await supabase
        .from("call_logs")
        .select("id, status, created_at")
        .in("agent_id", agentIds)
        .order("created_at", { ascending: false })
        .limit(10)
    : { data: [] };

  const knowledgeRes = await supabase
    .from("knowledge_items")
    .select("id, is_active");

  return (
    <DashboardClientPage
      agents={agentRes.data as Pick<AgentConfig, "id" | "agent_name" | "is_active" | "system_prompt" | "first_message" | "phone_number">[] | null}
      calls={callRes.data as Pick<CallLog, "id" | "status" | "created_at">[] | null}
      knowledgeCount={knowledgeRes.data?.length ?? 0}
    />
  );
}
