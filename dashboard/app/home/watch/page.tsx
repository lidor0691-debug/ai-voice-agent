import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { WatchShell } from "./WatchShell";
import {
  fetchMayaWatch,
  mapToWatchData,
  quietLiveState,
  liveFetchFailedState,
  type AuthIdentity,
} from "./maya-watch-api";
import { watchMock, type WatchData } from "./watch-mock";

/** Pull a non-empty string from any of the given keys on a metadata bag. */
function pickString(obj: Record<string, unknown> | undefined, ...keys: string[]): string | undefined {
  if (!obj) return undefined;
  for (const k of keys) {
    const v = obj[k];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return undefined;
}

/** Demo mode is opt-in and ONLY honored outside production. The mock
 *  contains fake people / fake KPIs / fake radar nodes — surfacing it in
 *  prod would misrepresent fabricated activity as real client data. */
function isDemoMode(): boolean {
  return process.env.NODE_ENV !== "production" && process.env.MAYA_WATCH_DEMO === "1";
}

export default async function WatchPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // Stage 4 — tenant scope. getUserContext returns:
  //   { isAdmin: true }                 → admin, see aggregated all
  //   { isAdmin: false, clientId: "…" } → fetch only that client's data
  //   null                              → unconfigured user
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

  // Stage 5 — only authenticated AND configured users (admin OR a client
  // with a real client_id) get live data. An unconfigured user (ctx=null)
  // skips the fetch so the dashboard never accidentally hands them
  // admin-aggregated data.
  const live = ctx ? await fetchMayaWatch(clientId) : null;

  // Decide what to render — page is the single source of truth so the
  // shell never has to guess.
  //
  //   live data        → mapToWatchData (real activity)
  //   ctx + null fetch → liveFetchFailedState (calm "still monitoring" copy
  //                       with no fake business activity)
  //   no ctx           → quietLiveState in prod; mock allowed only when
  //                       explicit dev-demo mode is on
  let initialData: WatchData;
  if (live) {
    initialData = mapToWatchData(live, identity);
  } else if (ctx) {
    initialData = liveFetchFailedState(identity);
  } else if (isDemoMode()) {
    initialData = watchMock;
  } else {
    initialData = quietLiveState(identity);
  }

  return <WatchShell initialData={initialData} />;
}

export const metadata = {
  title: "Maya · Watch",
};
