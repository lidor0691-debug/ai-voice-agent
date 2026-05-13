import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { HomeShell } from "../_shared/HomeShell";
import { HomeNavRail } from "../_shared/HomeNavRail";
import { resolveHomeIdentity } from "../_shared/identity";

// NOTE: 'briefings' is not yet in NAV_ORDER. Active key falls back to 'watch'.
export default async function BriefingsPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  const identity = resolveHomeIdentity(user);

  return (
    <HomeShell lang="he">
      <HomeNavRail lang="he" active="watch" user={identity} />
      <div className="lg:ps-[200px] min-h-full grid place-items-center">
        <div className="text-center text-[#0B1714]/60">
          <div className="maya-section-label mb-2">תדרוכים · בקרוב</div>
          <h1 className="text-2xl text-[#0B1714]/85 font-semibold">מסך התדרוכים יוטמע בהמשך</h1>
        </div>
      </div>
    </HomeShell>
  );
}

export const metadata = { title: "Maya · Briefings" };
