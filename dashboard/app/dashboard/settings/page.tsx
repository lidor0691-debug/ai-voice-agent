// dashboard/app/dashboard/settings/page.tsx

import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { SettingsClient } from "./settings-client";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);
  const isAdmin = ctx?.isAdmin ?? false;

  return <SettingsClient isAdmin={isAdmin} />;
}
