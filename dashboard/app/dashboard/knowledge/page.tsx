import { createSupabaseServerClient } from "@/lib/supabase-server";
import { createSupabaseAdminClient } from "@/lib/supabase-admin";
import { getUserContext } from "@/lib/user-context";
import { redirect } from "next/navigation";
import { AgentConfig, KnowledgeItem } from "@/types/database";
import { KnowledgeClient } from "@/components/knowledge/knowledge-client";

export const dynamic = "force-dynamic";

export default async function KnowledgePage() {
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx) redirect("/login");

  const admin = createSupabaseAdminClient();

  // Agents: admin sees all, client sees only their own
  let agentQuery = admin.from("agents_config").select("id, agent_name, client_id").eq("is_active", true).order("agent_name");
  if (!ctx.isAdmin) agentQuery = agentQuery.eq("client_id", ctx.clientId);
  const agentRes = await agentQuery;
  const agents = (agentRes.data ?? []) as (Pick<AgentConfig, "id" | "agent_name"> & { client_id: string })[];

  // Knowledge items: admin sees all, client sees only items for their agents
  let itemQuery = admin.from("knowledge_items").select("*").order("priority", { ascending: false });
  if (!ctx.isAdmin) {
    const agentIds = agents.map((a) => a.id);
    itemQuery = itemQuery.in("agent_id", agentIds.length > 0 ? agentIds : ["__none__"]);
  }
  const itemRes = await itemQuery;
  const items = (itemRes.data ?? []) as KnowledgeItem[];

  return <KnowledgeClient agents={agents} initialItems={items} />;
}
