import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { AgentConfig } from "@/types/database";

export async function GET(
  _: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { data, error } = await client
    .from("agents_config")
    .select("*")
    .eq("id", id)
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 404 });
  if (!ctx.isAdmin && data.client_id !== ctx.clientId)
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });

  return NextResponse.json(data);
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = (await req.json()) as Partial<AgentConfig>;

  if (!ctx.isAdmin) {
    const { data: existing, error: fetchError } = await client
      .from("agents_config")
      .select("client_id")
      .eq("id", id)
      .single();
    if (fetchError) return NextResponse.json({ error: fetchError.message }, { status: 404 });
    if (existing.client_id !== ctx.clientId)
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const { data, error } = await client
    .from("agents_config")
    .update(body)
    .eq("id", id)
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json(data);
}

export async function DELETE(
  _: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  if (!ctx.isAdmin) {
    const { data: existing, error: fetchError } = await client
      .from("agents_config")
      .select("client_id")
      .eq("id", id)
      .single();
    if (fetchError) return NextResponse.json({ error: fetchError.message }, { status: 404 });
    if (existing.client_id !== ctx.clientId)
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const { error } = await client
    .from("agents_config")
    .update({ is_active: false })
    .eq("id", id);

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ success: true });
}
