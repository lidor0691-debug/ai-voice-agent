import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";

export async function GET(req: NextRequest) {
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const agentId = req.nextUrl.searchParams.get("agent_id");

  if (!ctx.isAdmin) {
    if (!agentId) return NextResponse.json({ error: "agent_id is required" }, { status: 400 });

    const { data: agent, error: agentError } = await client
      .from("agents_config")
      .select("client_id")
      .eq("id", agentId)
      .single();

    if (agentError || !agent) return NextResponse.json({ error: "Not found" }, { status: 404 });
    if (agent.client_id !== ctx.clientId)
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  let query = client
    .from("knowledge_items")
    .select("*")
    .order("priority", { ascending: false });

  if (agentId) query = query.eq("agent_id", agentId);

  const { data, error } = await query;
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data);
}

export async function POST(req: NextRequest) {
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  if (!getUserContext(user)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();

  const { data, error } = await client
    .from("knowledge_items")
    .insert(body)
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json(data, { status: 201 });
}
