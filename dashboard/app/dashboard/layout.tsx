import { DashboardShell } from "@/components/layout/dashboard-shell";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { createSupabaseAdminClient } from "@/lib/supabase-admin";
import { getUserContext } from "@/lib/user-context";
import { redirect } from "next/navigation";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();

  if (!user) redirect("/login");

  const ctx = getUserContext(user);
  const isAdmin = ctx?.isAdmin ?? false;

  // Fetch first active agent for Dashboard Assistant
  const admin = createSupabaseAdminClient();
  const agentQuery = admin
    .from("agents_config")
    .select("id")
    .eq("is_active", true)
    .order("created_at", { ascending: false })
    .limit(1);
  if (!isAdmin && ctx && !ctx.isAdmin) agentQuery.eq("client_id", ctx.clientId);
  const { data: agentRows } = await agentQuery;
  const defaultAgentId = agentRows?.[0]?.id ?? null;

  return (
    <DashboardShell isAdmin={isAdmin} defaultAgentId={defaultAgentId}>
      {children}
    </DashboardShell>
  );
}
