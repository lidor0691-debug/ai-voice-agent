import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { WatchShell } from "./WatchShell";
import { fetchMayaWatch, mapToWatchData, type AuthIdentity } from "./maya-watch-api";

/** Pull a non-empty string from any of the given keys on a metadata bag. */
function pickString(obj: Record<string, unknown> | undefined, ...keys: string[]): string | undefined {
  if (!obj) return undefined;
  for (const k of keys) {
    const v = obj[k];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return undefined;
}

export default async function WatchPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // Stage 4 — tenant scope. getUserContext returns:
  //   { isAdmin: true }                 → admin, see aggregated all
  //   { isAdmin: false, clientId: "…" } → fetch only that client's data
  //   null                              → unconfigured user, see only mock fallback
  const ctx = getUserContext(user);
  const clientId = ctx && !ctx.isAdmin ? ctx.clientId : undefined;

  // Derive identity from the existing Supabase session (no new auth logic).
  // If user_metadata has nothing useful, mapToWatchData falls back to the
  // neutral product identity ("Maya Watch" / "מצב חי") — never the mock person.
  const meta = (user.user_metadata ?? {}) as Record<string, unknown>;
  const identity: AuthIdentity = {
    name: pickString(meta, "name", "full_name", "display_name"),
    role: pickString(meta, "business_name", "business", "company", "role"),
  };

  // Server-side fetch of live Maya Watch data with mock fallback only on
  // network failure — successful-but-empty responses degrade to a quiet
  // live state inside the mapper (no fake business activity).
  const live = await fetchMayaWatch(clientId);
  const initialData = live ? mapToWatchData(live, identity) : undefined;

  return <WatchShell initialData={initialData} />;
}

export const metadata = {
  title: "Maya · Watch",
};
