import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";

export async function GET(req: NextRequest) {
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const agentId = req.nextUrl.searchParams.get("agent_id");
  const limit = parseInt(req.nextUrl.searchParams.get("limit") ?? "50");

  let query = client
    .from("call_logs")
    .select("*, agents_config(agent_name)")
    .order("created_at", { ascending: false })
    .limit(limit);

  if (!ctx.isAdmin) {
    const { data: agents } = await client
      .from("agents_config")
      .select("id")
      .eq("client_id", ctx.clientId);
    const ownedIds = (agents ?? []).map((a: { id: string }) => a.id);
    if (ownedIds.length === 0) return NextResponse.json([]);
    if (agentId) {
      if (!ownedIds.includes(agentId))
        return NextResponse.json({ error: "Forbidden" }, { status: 403 });
      query = query.eq("agent_id", agentId);
    } else {
      query = query.in("agent_id", ownedIds);
    }
  } else if (agentId) {
    query = query.eq("agent_id", agentId);
  }

  const { data, error } = await query;
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data);
}

export async function POST(req: NextRequest) {
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();

  if (!ctx.isAdmin) {
    const targetAgentId = body?.agent_id;
    if (!targetAgentId) return NextResponse.json({ error: "agent_id required" }, { status: 400 });
    const { data: agent, error: agentErr } = await client
      .from("agents_config")
      .select("client_id")
      .eq("id", targetAgentId)
      .single();
    if (agentErr || !agent) return NextResponse.json({ error: "Agent not found" }, { status: 404 });
    if (agent.client_id !== ctx.clientId)
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const { data, error } = await client
    .from("call_logs")
    .insert(body)
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json(data, { status: 201 });
}
