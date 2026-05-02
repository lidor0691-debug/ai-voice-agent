import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { WatchShell } from "./WatchShell";
import { fetchMayaWatch, mapToWatchData } from "./maya-watch-api";

export default async function WatchPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // Server-side fetch of live Maya Watch data with mock fallback baked in.
  // mapToWatchData returns the mock when the backend is empty; passing
  // undefined when the fetch itself fails lets WatchShell apply the same fallback.
  const live = await fetchMayaWatch();
  const initialData = live ? mapToWatchData(live) : undefined;

  return <WatchShell initialData={initialData} />;
}

export const metadata = {
  title: "Maya · Watch",
};
