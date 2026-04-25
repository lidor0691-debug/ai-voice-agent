import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { AgentForm } from "@/components/agents/agent-form";

export const dynamic = "force-dynamic";

export default async function NewAgentPage() {
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);

  if (!ctx?.isAdmin) redirect("/dashboard/agents");

  return <AgentForm isAdmin />;
}
