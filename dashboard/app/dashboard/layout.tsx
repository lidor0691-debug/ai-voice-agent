import { DashboardShell } from "@/components/layout/dashboard-shell";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { redirect } from "next/navigation";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();

  if (!user) redirect("/login");

  const ctx = getUserContext(user);
  const isAdmin = ctx?.isAdmin ?? false;

  return <DashboardShell isAdmin={isAdmin}>{children}</DashboardShell>;
}
