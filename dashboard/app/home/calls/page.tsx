import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { HomeShell } from "../_shared/HomeShell";
import { HomeNavRail } from "../_shared/HomeNavRail";
import { watchMock } from "../watch/watch-mock";

export default async function CallsPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  return (
    <HomeShell lang="he">
      <HomeNavRail lang="he" active="calls" user={watchMock.user} />
      <div className="lg:ps-[200px] min-h-full grid place-items-center">
        <div className="text-center text-white/60">
          <div className="maya-section-label mb-2">שיחות קוליות · בקרוב</div>
          <h1 className="text-2xl text-white/85 font-semibold">מסך השיחות יוטמע בהמשך</h1>
        </div>
      </div>
    </HomeShell>
  );
}

export const metadata = { title: "Maya · Calls" };
