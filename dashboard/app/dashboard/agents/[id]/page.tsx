import { notFound } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { AgentConfig } from "@/types/database";
import { AgentPageTabs } from "@/components/agents/agent-page-tabs";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ id: string }>;
}

export default async function EditAgentPage({ params }: Props) {
  const { id } = await params;

  const { data, error } = await supabase
    .from("agents_config")
    .select("*")
    .eq("id", id)
    .single();

  if (error || !data) notFound();

  const agent = data as AgentConfig;

  return <AgentPageTabs agent={agent} />;
}
