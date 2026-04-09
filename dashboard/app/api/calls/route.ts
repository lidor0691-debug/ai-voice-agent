import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

export async function GET(req: NextRequest) {
  const agentId = req.nextUrl.searchParams.get("agent_id");
  const limit = parseInt(req.nextUrl.searchParams.get("limit") ?? "50");

  let query = supabase
    .from("call_logs")
    .select("*, agents_config(agent_name)")
    .order("created_at", { ascending: false })
    .limit(limit);

  if (agentId) query = query.eq("agent_id", agentId);

  const { data, error } = await query;
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data);
}

export async function POST(req: NextRequest) {
  const body = await req.json();

  const { data, error } = await supabase
    .from("call_logs")
    .insert(body)
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json(data, { status: 201 });
}
