import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import { ClientAsset } from "@/types/database";

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ client_id: string; id: string }> }
) {
  const { client_id, id } = await params;
  const body = await req.json() as Partial<ClientAsset>;

  const { data, error } = await supabase
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
  _: NextRequest,
  { params }: { params: Promise<{ client_id: string; id: string }> }
) {
  const { client_id, id } = await params;

  const { error } = await supabase
    .from("client_assets")
    .delete()
    .eq("id", id)
    .eq("client_id", client_id);

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ success: true });
}
