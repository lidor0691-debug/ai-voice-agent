import { supabase } from "@/lib/supabase";
import { AgentConfig, KnowledgeItem } from "@/types/database";
import { KnowledgeClient } from "@/components/knowledge/knowledge-client";

export const dynamic = "force-dynamic";

export default async function KnowledgePage() {
  const [agentRes, itemRes] = await Promise.all([
    supabase.from("agents_config").select("id, agent_name").order("agent_name"),
    supabase.from("knowledge_items").select("*").order("priority", { ascending: false }),
  ]);

  const agents = (agentRes.data ?? []) as Pick<AgentConfig, "id" | "agent_name">[];
  const items  = (itemRes.data ?? []) as KnowledgeItem[];

  return <KnowledgeClient agents={agents} initialItems={items} />;
}
