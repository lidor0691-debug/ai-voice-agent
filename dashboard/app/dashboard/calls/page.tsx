export const dynamic = "force-dynamic";

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { supabase } from "@/lib/supabase";
import { getUserContext } from "@/lib/user-context";
import { CallLog, AgentConfig } from "@/types/database";
import { CallsClientPage } from "./CallsClientPage";

type CallWithAgent = CallLog & { agents_config: Pick<AgentConfig, "agent_name"> | null };

export default async function CallsPage() {
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();
  const ctx = getUserContext(user);

  if (!ctx) return <CallsClientPage calls={null} error="Not authenticated" />;

  if (ctx.isAdmin) {
    const { data, error } = await supabase
      .from("call_logs")
      .select("*, agents_config(agent_name)")
      .order("created_at", { ascending: false })
      .limit(200);
    return <CallsClientPage calls={data as CallWithAgent[] | null} error={error?.message ?? null} />;
  }

  const { data: agents } = await supabase
    .from("agents_config")
    .select("id")
    .eq("client_id", ctx.clientId);

  const agentIds = (agents ?? []).map((a: Pick<AgentConfig, "id">) => a.id);
  if (agentIds.length === 0) return <CallsClientPage calls={[]} error={null} />;

  const { data, error } = await supabase
    .from("call_logs")
    .select("*, agents_config(agent_name)")
    .in("agent_id", agentIds)
    .order("created_at", { ascending: false })
    .limit(100);

  return <CallsClientPage calls={data as CallWithAgent[] | null} error={error?.message ?? null} />;
}
