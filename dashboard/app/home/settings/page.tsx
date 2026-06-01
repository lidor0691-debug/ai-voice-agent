import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { HomeShell } from "../_shared/HomeShell";
import { HomeNavRail } from "../_shared/HomeNavRail";
import { resolveHomeIdentity } from "../_shared/identity";
import { SettingsClient } from "../../dashboard/settings/settings-client";

export const dynamic = "force-dynamic";

// Scoped retheme. The legacy SettingsClient was built for the dark
// /dashboard chrome (purple CTAs, surface-0/1/3 near-black backgrounds,
// brand-400 purple links). We re-skin those descendant classes here only
// — every selector lives under `.maya-home-settings`, so the legacy
// /dashboard/settings page is untouched. Palette tokens (--canvas,
// --paper, --ink*, --rule*, --bronze, --forest, --cream) come from
// home.css.ts which puts them on :root, so they are visible here.
const scopedCss = String.raw`
.maya-home-settings { display: flex; min-height: 100%; }
.maya-home-settings > div { flex: 1 1 auto; }
.maya-home-settings .max-w-2xl { margin-left: auto; margin-right: auto; }

/* Surfaces — neutralize dark dashboard backgrounds onto the cream canvas */
.maya-home-settings .bg-surface-0,
.maya-home-settings .bg-surface-1 { background: var(--canvas) !important; }
.maya-home-settings .bg-surface-3,
.maya-home-settings .bg-surface-3\/50 { background: var(--paper) !important; }

/* Cards — paper surface with the same rule border the rest of /home uses */
.maya-home-settings .card {
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: var(--radius-sm);
  box-shadow: 0 1px 2px rgba(26, 26, 20, 0.03);
}

/* Borders — legacy border-border class mapped to the Maya rule line */
.maya-home-settings .border-border { border-color: var(--rule) !important; }

/* Text — re-tone dashboard greys/whites onto warm ink */
.maya-home-settings .text-white { color: var(--ink) !important; }
.maya-home-settings .text-gray-300,
.maya-home-settings .text-gray-400,
.maya-home-settings .text-gray-500,
.maya-home-settings .text-gray-600 { color: var(--ink-3) !important; }

/* Links / brand accents — bronze instead of legacy purple */
.maya-home-settings .text-brand-400,
.maya-home-settings .text-brand-300,
.maya-home-settings .hover\:text-brand-300:hover,
.maya-home-settings .hover\:text-brand-400:hover { color: var(--bronze) !important; }

/* Inputs / selects — ivory paper, ink text, bronze focus (no purple ring) */
.maya-home-settings input,
.maya-home-settings select,
.maya-home-settings textarea {
  background: var(--paper) !important;
  color: var(--ink) !important;
  border-color: var(--rule-2) !important;
  border-radius: 10px;
}
.maya-home-settings input::placeholder,
.maya-home-settings textarea::placeholder { color: var(--ink-4) !important; }
.maya-home-settings input:focus,
.maya-home-settings input:focus-visible,
.maya-home-settings select:focus,
.maya-home-settings select:focus-visible,
.maya-home-settings textarea:focus,
.maya-home-settings textarea:focus-visible {
  outline: 2px solid var(--bronze) !important;
  outline-offset: 1px !important;
  --tw-ring-color: transparent !important;
  box-shadow: none !important;
  border-color: var(--rule-2) !important;
}

/* Save CTA — Maya dark-green button with cream label, bronze focus ring */
.maya-home-settings .btn-primary {
  background: var(--forest);
  color: var(--cream);
  border: 1px solid var(--forest);
  border-radius: 10px;
  padding: 8px 14px;
  font-size: 13px;
  line-height: 1.2;
  font-weight: 500;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}
.maya-home-settings .btn-primary:hover {
  background: var(--forest-2);
  border-color: var(--forest-2);
}
.maya-home-settings .btn-primary:focus-visible {
  outline: 2px solid var(--bronze);
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
