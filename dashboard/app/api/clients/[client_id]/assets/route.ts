import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { ClientAsset } from "@/types/database";

export async function GET(
  _: NextRequest,
  { params }: { params: Promise<{ client_id: string }> }
) {
  const { client_id } = await params;
  const client = await createSupabaseServerClient();

  const { data, error } = await client
    .from("client_assets")
    .select("*")
    .eq("client_id", client_id)
    .order("sort_order", { ascending: true })
    .order("created_at", { ascending: true });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data);
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ client_id: string }> }
) {
  const { client_id } = await params;
  const client = await createSupabaseServerClient();
  const body = await req.json() as Omit<ClientAsset, "id" | "client_id" | "created_at">;

  const { data, error } = await client
    .from("client_assets")
    .insert({ ...body, client_id })
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json(data, { status: 201 });
}
