import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { createSupabaseAdminClient } from "@/lib/supabase-admin";
import { getUserContext } from "@/lib/user-context";
import { KnowledgeItem } from "@/types/database";

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const body = (await req.json()) as Partial<KnowledgeItem>;

  const admin = createSupabaseAdminClient();

  if (!ctx.isAdmin) {
    const { data: existing, error: fetchError } = await admin
      .from("knowledge_items")
      .select("agents_config(client_id)")
      .eq("id", id)
      .single();
    if (fetchError || !existing) return NextResponse.json({ error: "Not found" }, { status: 404 });
    const ac = existing.agents_config as { client_id: string }[] | { client_id: string } | null;
    const ownerClientId = Array.isArray(ac) ? ac[0]?.client_id : ac?.client_id;
    if (ownerClientId !== ctx.clientId)
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const { data, error } = await admin
    .from("knowledge_items")
    .update(body)
    .eq("id", id)
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json(data);
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const admin = createSupabaseAdminClient();

  if (!ctx.isAdmin) {
    const { data: existing, error: fetchError } = await admin
      .from("knowledge_items")
      .select("agents_config(client_id)")
      .eq("id", id)
      .single();
    if (fetchError || !existing) return NextResponse.json({ error: "Not found" }, { status: 404 });
    const ac2 = existing.agents_config as { client_id: string }[] | { client_id: string } | null;
    const ownerClientId2 = Array.isArray(ac2) ? ac2[0]?.client_id : ac2?.client_id;
    if (ownerClientId2 !== ctx.clientId)
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const { error } = await admin
    .from("knowledge_items")
    .delete()
    .eq("id", id);

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ success: true });
}
