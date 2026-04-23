import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { createSupabaseAdminClient } from "@/lib/supabase-admin";
import { getUserContext } from "@/lib/user-context";

export async function GET(req: NextRequest) {
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const agentId = req.nextUrl.searchParams.get("agent_id");
  const admin = createSupabaseAdminClient();

  if (!ctx.isAdmin) {
    if (!agentId) return NextResponse.json({ error: "agent_id is required" }, { status: 400 });

    const { data: agent, error: agentError } = await admin
      .from("agents_config")
      .select("client_id")
      .eq("id", agentId)
      .single();

    if (agentError || !agent) return NextResponse.json({ error: "Not found" }, { status: 404 });
    if (agent.client_id !== ctx.clientId)
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  let query = admin
    .from("knowledge_items")
    .select("*")
    .order("priority", { ascending: false });

  if (agentId) query = query.eq("agent_id", agentId);

  const { data, error } = await query;
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data);
}

export async function POST(req: NextRequest) {
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();
  if (!getUserContext(user)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();

  const admin = createSupabaseAdminClient();
  const { data, error } = await admin
    .from("knowledge_items")
    .insert(body)
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json(data, { status: 201 });
}
