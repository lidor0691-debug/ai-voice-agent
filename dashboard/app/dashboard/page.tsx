export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { AgentConfig, CallLog } from "@/types/database";
import { DashboardClientPage } from "./DashboardClientPage";

export default async function DashboardPage() {
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);

  if (!ctx) {
    return <DashboardClientPage agents={null} calls={null} knowledgeCount={0} insights={null} />;
  }

  const agentQuery = client
    .from("agents_config")
    .select("id, agent_name, is_active, system_prompt, first_message, phone_number")
    .eq("is_active", true)
    .order("created_at", { ascending: false });
  if (!ctx.isAdmin) agentQuery.eq("client_id", ctx.clientId);
  const agentRes = await agentQuery;

  const agentIds = (agentRes.data ?? []).map((a: Pick<AgentConfig, "id">) => a.id);
  const callRes = agentIds.length > 0
    ? await client
        .from("call_logs")
        .select("id, status, created_at")
        .in("agent_id", agentIds)
        .order("created_at", { ascending: false })
        .limit(10)
    : { data: [] };

  const knowledgeRes = await client.from("knowledge_items").select("id, is_active");

  const insightQuery = client
    .from("lead_intelligence_insights")
    .select("insight_type, title, frequency_count, created_at")
    .order("created_at", { ascending: false })
    .limit(20);
  if (!ctx.isAdmin) insightQuery.eq("client_id", ctx.clientId);
  const insightRes = await insightQuery;

  return (
    <DashboardClientPage
      agents={agentRes.data as Pick<AgentConfig, "id" | "agent_name" | "is_active" | "system_prompt" | "first_message" | "phone_number">[] | null}
      calls={callRes.data as Pick<CallLog, "id" | "status" | "created_at">[] | null}
      knowledgeCount={knowledgeRes.data?.length ?? 0}
      insights={insightRes.data as { insight_type: string; title: string; frequency_count: number; created_at: string }[] | null}
    />
  );
}
