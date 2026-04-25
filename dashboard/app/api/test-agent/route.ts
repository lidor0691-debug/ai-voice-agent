import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";

export async function POST(req: NextRequest) {
  // ── Auth + ownership ──────────────────────────────────────────────
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { agent_id, messages, system_prompt } = await req.json();

  if (!ctx.isAdmin) {
    if (!agent_id) return NextResponse.json({ error: "agent_id required" }, { status: 400 });
    const { data: agent, error: fetchErr } = await client
      .from("agents_config")
      .select("client_id")
      .eq("id", agent_id)
      .single();
    if (fetchErr || !agent) return NextResponse.json({ error: "Agent not found" }, { status: 404 });
    if (agent.client_id !== ctx.clientId)
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  // ── Proxy to backend ─────────────────────────────────────────────
  const backendUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

  try {
    const res = await fetch(`${backendUrl}/api/test-agent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id, messages, system_prompt }),
      signal: AbortSignal.timeout(15000),
    });

    if (!res.ok) {
      return NextResponse.json(
        { error: "Backend returned an error" },
        { status: res.status }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { error: "Could not connect to backend" },
      { status: 502 }
    );
  }
}
