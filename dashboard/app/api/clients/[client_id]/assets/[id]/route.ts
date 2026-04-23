import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { createSupabaseAdminClient } from "@/lib/supabase-admin";
import { getUserContext } from "@/lib/user-context";
import { ClientAsset } from "@/types/database";

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ client_id: string; id: string }> }
) {
  const { client_id, id } = await params;
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  if (!ctx.isAdmin && ctx.clientId !== client_id) return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  const body = await req.json() as Partial<ClientAsset>;

  const admin = createSupabaseAdminClient();
  const { data, error } = await admin
    .from("client_assets")
    .update(body)
    .eq("id", id)
    .eq("client_id", client_id)
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json(data);
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ client_id: string; id: string }> }
) {
  const { client_id, id } = await params;
  const authClient = await createSupabaseServerClient();
  const { data: { user } } = await authClient.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  if (!ctx.isAdmin && ctx.clientId !== client_id) return NextResponse.json({ error: "Forbidden" }, { status: 403 });

  const admin = createSupabaseAdminClient();
  const { error } = await admin
    .from("client_assets")
    .delete()
    .eq("id", id)
    .eq("client_id", client_id);

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ success: true });
}
