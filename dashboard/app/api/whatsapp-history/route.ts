import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";

export const dynamic = "force-dynamic";

interface ConversationMessage {
  role: "user" | "assistant" | string;
  content: string;
  timestamp?: string;
}

export async function GET(req: NextRequest): Promise<NextResponse> {
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const phone = req.nextUrl.searchParams.get("phone");
  console.log("[/api/whatsapp-history] phone=%s isAdmin=%s clientId=%s", phone, ctx.isAdmin, ctx.isAdmin ? "(admin)" : ctx.clientId);
  if (!phone) return NextResponse.json({ messages: [] });

  const query = client
    .from("whatsapp_conversations")
    .select("messages_json, client_id, updated_at")
    .eq("phone", phone)
    .limit(1);

  if (!ctx.isAdmin) query.eq("client_id", ctx.clientId);

  const { data, error } = await query;
  if (error) {
    console.error("[/api/whatsapp-history] Supabase error:", error.message);
    return NextResponse.json({ messages: [], debug: { phone, error: error.message } });
  }

  const row = (data ?? [])[0];
  console.log("[/api/whatsapp-history] rows=%d row_client_id=%s", (data ?? []).length, row?.client_id);
  if (!row) return NextResponse.json({ messages: [], debug: { phone, reason: "no_row" } });

  // Defense in depth: even if RLS-bypassed somehow, ensure the row matches the user's client_id.
  if (!ctx.isAdmin && row.client_id !== ctx.clientId) {
    console.warn("[/api/whatsapp-history] client_id mismatch: row=%s ctx=%s", row.client_id, ctx.clientId);
    return NextResponse.json({ messages: [], debug: { phone, reason: "client_mismatch" } });
  }

  let messages: ConversationMessage[] = [];
  const raw = row.messages_json;
  if (Array.isArray(raw)) {
    messages = raw as ConversationMessage[];
  } else if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) messages = parsed;
    } catch {
      messages = [];
    }
  }

  return NextResponse.json({ messages, updated_at: row.updated_at ?? null });
}
