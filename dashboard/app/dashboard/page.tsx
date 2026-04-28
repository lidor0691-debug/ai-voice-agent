export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { createSupabaseAdminClient } from "@/lib/supabase-admin";
import { getUserContext } from "@/lib/user-context";
import { AgentConfig, CallLog } from "@/types/database";
import { DashboardClientPage } from "./DashboardClientPage";

export default async function DashboardPage() {
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);

  if (!ctx) {
    return <DashboardClientPage agents={null} calls={null} knowledgeCount={0} insights={null} injectionEvents={null} winSignals={null} />;
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

  const admin = createSupabaseAdminClient();
  let knowledgeRes: { data: { id: string; is_active: boolean }[] | null };
  if (ctx.isAdmin) {
    knowledgeRes = await admin.from("knowledge_items").select("id, is_active");
  } else if (agentIds.length === 0) {
    knowledgeRes = { data: [] };
  } else {
    knowledgeRes = await admin
      .from("knowledge_items")
      .select("id, is_active")
      .in("agent_id", agentIds);
  }

  const insightQuery = client
    .from("lead_intelligence_insights")
    .select("insight_type, title, frequency_count, created_at")
    .order("created_at", { ascending: false })
    .limit(20);
  if (!ctx.isAdmin) insightQuery.eq("client_id", ctx.clientId);
  const insightRes = await insightQuery;

  const winQuery = client
    .from("lead_intelligence_insights")
    .select("title, created_at")
    .eq("insight_type", "win_signal")
    .order("created_at", { ascending: false })
    .limit(20);
  if (!ctx.isAdmin) winQuery.eq("client_id", ctx.clientId);
  const winRes = await winQuery;

  const injectionQuery = client
    .from("audit_logs")
    .select("created_at, new_data")
    .eq("table_name", "lead_intelligence_injection")
    .order("created_at", { ascending: false })
    .limit(10);
  if (!ctx.isAdmin) injectionQuery.eq("new_data->>client_id", ctx.clientId);
  const injectionRes = await injectionQuery;

  return (
    <DashboardClientPage
      agents={agentRes.data as Pick<AgentConfig, "id" | "agent_name" | "is_active" | "system_prompt" | "first_message" | "phone_number">[] | null}
      calls={callRes.data as Pick<CallLog, "id" | "status" | "created_at">[] | null}
      knowledgeCount={knowledgeRes.data?.length ?? 0}
      insights={insightRes.data as { insight_type: string; title: string; frequency_count: number; created_at: string }[] | null}
      injectionEvents={injectionRes.data as { created_at: string; new_data: { client_id: string; rule_key: string; sentence: string; weight: number } }[] | null}
      winSignals={winRes.data as { title: string; created_at: string }[] | null}
    />
  );
}
