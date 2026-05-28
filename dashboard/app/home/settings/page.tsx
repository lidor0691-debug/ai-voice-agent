import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { HomeShell } from "../_shared/HomeShell";
import { HomeNavRail } from "../_shared/HomeNavRail";
import { resolveHomeIdentity } from "../_shared/identity";
import { SettingsClient } from "../../dashboard/settings/settings-client";

export const dynamic = "force-dynamic";

export default async function HomeSettingsPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const identity = resolveHomeIdentity(user);
  const ctx = getUserContext(user);
  const isAdmin = ctx?.isAdmin ?? false;

  return (
    <HomeShell lang="he">
      <HomeNavRail lang="he" active="settings" user={identity} />
      <div className="lg:ps-[200px] min-h-full flex">
        <SettingsClient isAdmin={isAdmin} />
      </div>
    </HomeShell>
  );
}

export const metadata = { title: "Maya · Settings" };
