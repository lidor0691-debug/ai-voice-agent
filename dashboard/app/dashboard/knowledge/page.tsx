import { createSupabaseServerClient } from "@/lib/supabase-server";
import { AgentConfig, KnowledgeItem } from "@/types/database";
import { KnowledgeClient } from "@/components/knowledge/knowledge-client";

export const dynamic = "force-dynamic";

export default async function KnowledgePage() {
  const client = await createSupabaseServerClient();
  const [agentRes, itemRes] = await Promise.all([
    client.from("agents_config").select("id, agent_name").eq("is_active", true).order("agent_name"),
    client.from("knowledge_items").select("*").order("priority", { ascending: false }),
  ]);

  const agents = (agentRes.data ?? []) as Pick<AgentConfig, "id" | "agent_name">[];
  const items  = (itemRes.data ?? []) as KnowledgeItem[];

  return <KnowledgeClient agents={agents} initialItems={items} />;
}
