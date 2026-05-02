import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { WatchShell } from "./WatchShell";

export default async function WatchPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  return <WatchShell />;
}

export const metadata = {
  title: "Maya · Watch",
};
