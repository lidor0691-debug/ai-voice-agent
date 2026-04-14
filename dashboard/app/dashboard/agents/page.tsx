export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { supabase } from "@/lib/supabase";
import { getUserContext } from "@/lib/user-context";
import { AgentConfig } from "@/types/database";
import { AgentsClientPage } from "./AgentsClientPage";

export default async function AgentsPage() {
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();
  const ctx = getUserContext(user);

  if (!ctx) return <AgentsClientPage agents={null} error="Not authenticated" />;

  const query = supabase
    .from("agents_config")
    .select("*")
    .order("created_at", { ascending: false });
  if (!ctx.isAdmin) query.eq("client_id", ctx.clientId);

  const { data, error } = await query;
  return (
    <AgentsClientPage
      agents={data as AgentConfig[] | null}
      error={error?.message ?? null}
    />
  );
}
