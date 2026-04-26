import { NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";

export async function GET() {
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);

  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const query = client
    .from("conversion_leak_signals")
    .select("id,created_at,lead_id,lead_phone,lead_name,signal_type,detail,suggested_action,status")
    .eq("status", "open")
    .order("created_at", { ascending: false })
    .limit(20);

  if (!ctx.isAdmin) query.eq("client_id", ctx.clientId);

  const { data, error } = await query;
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ signals: data ?? [], count: data?.length ?? 0 });
}
