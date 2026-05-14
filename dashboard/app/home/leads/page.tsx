import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { createSupabaseAdminClient } from "@/lib/supabase-admin";
import { getUserContext } from "@/lib/user-context";
import { HomeShell } from "../_shared/HomeShell";
import { HomeNavRail } from "../_shared/HomeNavRail";
import { resolveHomeIdentity } from "../_shared/identity";
import { LeadsTable, type LeadRow } from "./LeadsTable";

/** Normalize a phone for dedupe key. Conservative: handles "whatsapp:" prefix
 *  and the common Israeli `0XX…` → `+972XX…` rewrite. Otherwise passthrough. */
function normalizePhone(input: string | null | undefined): string {
  if (!input) return "";
  let p = input.trim();
  if (p.startsWith("whatsapp:")) p = p.slice("whatsapp:".length).trim();
  if (p.startsWith("+")) return p;
  if (/^0\d{8,9}$/.test(p)) return `+972${p.slice(1)}`;
  return p;
}

interface MayaWatchLeadRow {
  id: string;
  client_id: string | null;
  phone: string | null;
  name: string | null;
  booked: boolean | null;
  booked_at: string | null;
  followup_sent_at: string | null;
  created_at: string;
}

/** Derive a coarse status label for a Maya Watch-only lead. */
function deriveMayaWatchStatus(r: MayaWatchLeadRow): string {
  if (r.booked) return "booked";
  if (r.followup_sent_at) return "followup_pending";
  return "new";
}

export default async function LeadsPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  const identity = resolveHomeIdentity(user);
  const ctx = getUserContext(user);

  let leads: LeadRow[] = [];

  if (ctx) {
    // Legacy leads — user-scoped client, RLS-enforced.
    const legacyQuery = supabase
      .from("leads")
      .select("id, created_at, name, phone, source, status, appointment_at, last_whatsapp_inbound_at, client_id")
      .neq("source", "browser_voice")
      .not("phone", "is", null)
      .order("created_at", { ascending: false })
      .limit(50);
    if (!ctx.isAdmin) legacyQuery.eq("client_id", ctx.clientId);

    // Maya Watch leads — admin client (RLS bypass) + code-side client_id scope.
    // Mirrors the pattern used by /api/whatsapp-history.
    const admin = createSupabaseAdminClient();
    const mwQuery = admin
      .from("maya_watch_leads")
      .select("id, client_id, phone, name, booked, booked_at, followup_sent_at, created_at")
      .not("phone", "is", null)
      .order("created_at", { ascending: false })
      .limit(50);
    if (!ctx.isAdmin) mwQuery.eq("client_id", ctx.clientId);

    const [legacyRes, mwRes] = await Promise.all([legacyQuery, mwQuery]);

    if (legacyRes.error) {
      console.error("[home/leads] legacy fetch failed:", legacyRes.error.message);
    }
    if (mwRes.error) {
      console.error("[home/leads] maya_watch_leads fetch failed:", mwRes.error.message);
    }

    const legacy = (legacyRes.data ?? []) as LeadRow[];
    const mw = (mwRes.data ?? []) as MayaWatchLeadRow[];

    // Dedupe key — legacy rows win when (phone, client_id) overlaps.
    const seen = new Set<string>();
    for (const l of legacy) {
      seen.add(`${normalizePhone(l.phone)}|${l.client_id ?? ""}`);
    }

    const merged: LeadRow[] = [...legacy];
    for (const r of mw) {
      const key = `${normalizePhone(r.phone)}|${r.client_id ?? ""}`;
      if (seen.has(key)) continue;
      // Defensive — extra `client_id` re-check for non-admins. RLS bypass
      // means we trust nothing the row carries; the query filter is the
      // primary guard, this is belt-and-suspenders.
      if (!ctx.isAdmin && r.client_id !== ctx.clientId) continue;
      seen.add(key);
      merged.push({
        id: r.id,
        created_at: r.created_at,
        name: r.name,
        phone: r.phone ?? "",
        source: "whatsapp",
        status: deriveMayaWatchStatus(r),
        appointment_at: null,
        last_whatsapp_inbound_at: null,
        client_id: r.client_id,
      });
    }

    merged.sort((a, b) => (a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : 0));
    leads = merged.slice(0, 50);
  }

  return (
    <HomeShell lang="he">
      <HomeNavRail lang="he" active="leads" user={identity} />
      <div className="lg:ps-[200px] min-h-full">
        <div className="max-w-5xl mx-auto px-6 py-8 maya-hebrew">
          <header className="mb-6 flex items-baseline justify-between gap-3">
            <h1 className="text-2xl text-[#0B1714]/90 font-semibold">לידים</h1>
            <span className="text-[12px] text-[#0B1714]/55 tnum">
              {leads.length > 0 ? `${leads.length} מתוך אחרונים` : "—"}
            </span>
          </header>

          <LeadsTable leads={leads} />
        </div>
      </div>
    </HomeShell>
  );
}

export const metadata = { title: "Maya · Leads" };
