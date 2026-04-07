import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

export async function GET() {
  const { data, error } = await supabase
    .from("agents_config")
    .select("*")
    .order("created_at", { ascending: false });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data);
}

export async function POST(req: NextRequest) {
  const body = await req.json();

  // 1. Create a clients row for this new agent
  const clientName: string =
    (body.business_name as string | undefined) ||
    (body.agent_name as string | undefined) ||
    "Unknown";

  const { data: clientData, error: clientError } = await supabase
    .from("clients")
    .insert({ name: clientName })
    .select()
    .single();

  if (clientError) {
    return NextResponse.json({ error: clientError.message }, { status: 400 });
  }

  // 2. Create the agent with client_id set
  const { data, error } = await supabase
    .from("agents_config")
    .insert({ ...body, client_id: clientData.id })
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json(data, { status: 201 });
}
