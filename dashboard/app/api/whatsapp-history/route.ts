import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { createSupabaseAdminClient } from "@/lib/supabase-admin";
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
  const ctxClientId = ctx.isAdmin ? null : ctx.clientId;
  console.log("[/api/whatsapp-history] phone=%s isAdmin=%s clientId=%s", phone, ctx.isAdmin, ctxClientId ?? "(admin)");
  if (!phone) return NextResponse.json({ messages: [] });

  // whatsapp_conversations has RLS that blocks reads via the user-scoped client.
  // Use the admin client to bypass RLS, then enforce client_id scoping in code below.
  const admin = createSupabaseAdminClient();
  const query = admin
    .from("whatsapp_conversations")
    .select("messages_json, client_id, updated_at")
    .eq("phone", phone)
    .limit(1);

  const { data, error } = await query;
  if (error) {
    console.error("[/api/whatsapp-history] Supabase error:", error.message);
    return NextResponse.json({
      messages: [],
      debug: { phone, ctxClientId, isAdmin: ctx.isAdmin, rowsFound: 0, reason: "query_error", error: error.message },
    });
  }

  const rowsFound = (data ?? []).length;
  const row = (data ?? [])[0];
  console.log("[/api/whatsapp-history] rows=%d row_client_id=%s", rowsFound, row?.client_id);
  if (!row) {
    return NextResponse.json({
      messages: [],
      debug: { phone, ctxClientId, isAdmin: ctx.isAdmin, rowsFound, reason: "no_row" },
    });
  }

  // Enforce client_id scoping in code (since we bypassed RLS).
  // Admin sees all; non-admin sees only rows whose client_id matches their own.
  // NULL-client_id rows (un-backfilled) are never visible to non-admins.
  if (!ctx.isAdmin && row.client_id !== ctx.clientId) {
    console.warn("[/api/whatsapp-history] client_id mismatch: row=%s ctx=%s", row.client_id, ctx.clientId);
    return NextResponse.json({
      messages: [],
      debug: {
        phone, ctxClientId, isAdmin: ctx.isAdmin, rowsFound,
        rowClientId: row.client_id, reason: "client_mismatch",
      },
    });
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
