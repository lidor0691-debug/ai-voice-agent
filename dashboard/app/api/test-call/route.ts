import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";

export async function POST(req: NextRequest) {
  // ── Auth + ownership ──────────────────────────────────────────────
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const agentId = body.agent_id;

  if (!ctx.isAdmin) {
    if (!agentId) return NextResponse.json({ error: "agent_id required" }, { status: 400 });
    const { data: agent, error: fetchErr } = await client
      .from("agents_config")
      .select("client_id")
      .eq("id", agentId)
      .single();
    if (fetchErr || !agent) return NextResponse.json({ error: "Agent not found" }, { status: 404 });
    if (agent.client_id !== ctx.clientId)
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  // ── Proxy to backend ─────────────────────────────────────────────
  const backendUrl = process.env.API_BASE_URL;

  if (!backendUrl && process.env.NODE_ENV === "production") {
    return NextResponse.json({ error: "API_BASE_URL is not configured on this server" }, { status: 503 });
  }

  const resolvedUrl = backendUrl ?? "http://localhost:8000";

  try {
    const res = await fetch(`${resolvedUrl}/test-call`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(15000),
    });

    const data = await res.json();
    if (!res.ok) {
      return NextResponse.json(data, { status: res.status });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "Failed to initiate test call" }, { status: 500 });
  }
}
