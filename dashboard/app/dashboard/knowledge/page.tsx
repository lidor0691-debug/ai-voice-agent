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
  if (!getUserContext(user)) redirect("/login");

  const admin = createSupabaseAdminClient();
  const [agentRes, itemRes] = await Promise.all([
    admin.from("agents_config").select("id, agent_name").eq("is_active", true).order("agent_name"),
    admin.from("knowledge_items").select("*").order("priority", { ascending: false }),
  ]);

  const agents = (agentRes.data ?? []) as Pick<AgentConfig, "id" | "agent_name">[];
  const items  = (itemRes.data ?? []) as KnowledgeItem[];

  return <KnowledgeClient agents={agents} initialItems={items} />;
}
