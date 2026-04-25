import { notFound } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { AgentConfig } from "@/types/database";
import { AgentPageTabs } from "@/components/agents/agent-page-tabs";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ id: string }>;
}

export default async function EditAgentPage({ params }: Props) {
  const { id } = await params;
  const client = await createSupabaseServerClient();

  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);
  const isAdmin = ctx?.isAdmin ?? false;

  const { data, error } = await client
    .from("agents_config")
    .select("*")
    .eq("id", id)
    .single();

  if (error || !data) notFound();

  const agent = data as AgentConfig;

  return <AgentPageTabs agent={agent} isAdmin={isAdmin} />;
}
