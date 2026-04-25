export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { AgentConfig } from "@/types/database";
import { AgentsClientPage } from "./AgentsClientPage";

export default async function AgentsPage() {
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);

  if (!ctx) return <AgentsClientPage agents={null} error="Not authenticated" />;

  const query = client
    .from("agents_config")
    .select("*")
    .eq("is_active", true)
    .order("created_at", { ascending: false });
  if (!ctx.isAdmin) query.eq("client_id", ctx.clientId);

  const { data, error } = await query;
  return (
    <AgentsClientPage
      agents={data as AgentConfig[] | null}
      error={error?.message ?? null}
      isAdmin={ctx.isAdmin}
    />
  );
}
