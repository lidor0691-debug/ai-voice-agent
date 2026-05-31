import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { HomeShell } from "../_shared/HomeShell";
import { HomeNavRail } from "../_shared/HomeNavRail";
import { resolveHomeIdentity } from "../_shared/identity";
import { SettingsClient } from "../../dashboard/settings/settings-client";

export const dynamic = "force-dynamic";

// Scoped overrides so the legacy SettingsClient (built for the dark
// /dashboard chrome) reads as part of the ivory /home surface. Centers the
// max-w-2xl column inside the flex parent (RTL was anchoring it to the
// right edge) and retones the purple `.btn-primary` CTA into the Maya
// dark-green/ivory palette. Scoped under `.maya-home-settings` so the
// legacy /dashboard/settings page is untouched.
const scopedCss = `
.maya-home-settings { display: flex; min-height: 100%; }
.maya-home-settings > div { flex: 1 1 auto; }
.maya-home-settings .max-w-2xl { margin-left: auto; margin-right: auto; }
.maya-home-settings .btn-primary {
  background: #0B1714;
  color: #F8F4EC;
  border: 1px solid #0B1714;
  border-radius: 10px;
  padding: 8px 14px;
  font-size: 13px;
  line-height: 1.2;
  font-weight: 500;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}
.maya-home-settings .btn-primary:hover { background: #1A2E29; border-color: #1A2E29; }
.maya-home-settings .btn-primary:focus-visible {
  outline: 2px solid #C9A96E;
  outline-offset: 2px;
}
`;

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
      <style dangerouslySetInnerHTML={{ __html: scopedCss }} />
      <div className="maya-home-settings lg:ps-[200px] min-h-full">
        <SettingsClient isAdmin={isAdmin} />
      </div>
    </HomeShell>
  );
}

export const metadata = { title: "Maya · Settings" };
