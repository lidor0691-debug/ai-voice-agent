export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { supabase } from "@/lib/supabase";
import { getUserContext } from "@/lib/user-context";
import { AgentConfig, CallLog } from "@/types/database";
import { DashboardClientPage } from "./DashboardClientPage";

export default async function DashboardPage() {
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();
  const ctx = getUserContext(user);

  if (!ctx) {
    return <DashboardClientPage agents={null} calls={null} knowledgeCount={0} />;
  }

  const agentQuery = supabase
    .from("agents_config")
    .select("id, agent_name, is_active, system_prompt, first_message, phone_number")
    .order("created_at", { ascending: false });
  if (!ctx.isAdmin) agentQuery.eq("client_id", ctx.clientId);
  const agentRes = await agentQuery;

  const agentIds = (agentRes.data ?? []).map((a: Pick<AgentConfig, "id">) => a.id);
  const callRes = agentIds.length > 0
    ? await supabase
        .from("call_logs")
        .select("id, status, created_at")
        .in("agent_id", agentIds)
        .order("created_at", { ascending: false })
        .limit(10)
    : { data: [] };

  const knowledgeRes = await supabase.from("knowledge_items").select("id, is_active");

  return (
    <DashboardClientPage
      agents={agentRes.data as Pick<AgentConfig, "id" | "agent_name" | "is_active" | "system_prompt" | "first_message" | "phone_number">[] | null}
      calls={callRes.data as Pick<CallLog, "id" | "status" | "created_at">[] | null}
      knowledgeCount={knowledgeRes.data?.length ?? 0}
    />
  );
}
