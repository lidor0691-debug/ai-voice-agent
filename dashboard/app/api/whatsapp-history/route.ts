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

/**
 * Fallback: read recent Maya Watch messages for this phone (and tenant) and
 * map them into the same {role, content, timestamp} shape the drawer
 * already consumes. Read-only. Returns at most the last 50 messages,
 * oldest→newest.
 *
 * The maya_watch_messages table has no `phone` column — it keys by
 * `lead_id`. So we first resolve the lead via maya_watch_leads (admin
 * client, with code-side client_id scoping for non-admins), then load
 * messages by that lead_id. Returns [] on any miss or error.
 */
async function fetchMayaWatchHistory(
  admin: ReturnType<typeof createSupabaseAdminClient>,
  phone: string,
  ctxClientId: string | null,
): Promise<ConversationMessage[]> {
  const leadQuery = admin
    .from("maya_watch_leads")
    .select("id, client_id")
    .eq("phone", phone)
    .limit(1);
  if (ctxClientId !== null) leadQuery.eq("client_id", ctxClientId);

  const { data: leadRows, error: leadErr } = await leadQuery;
  if (leadErr) {
    console.error("[/api/whatsapp-history] mw lead lookup failed:", leadErr.message);
    return [];
  }
  const leadRow = (leadRows ?? [])[0];
  if (!leadRow) return [];

  // Belt-and-suspenders client_id re-check.
  if (ctxClientId !== null && leadRow.client_id !== ctxClientId) {
    return [];
  }

  const msgQuery = admin
    .from("maya_watch_messages")
    .select("direction, body, ts")
    .eq("lead_id", leadRow.id)
    .order("ts", { ascending: true })
    .limit(50);

  const { data: msgRows, error: msgErr } = await msgQuery;
  if (msgErr) {
    console.error("[/api/whatsapp-history] mw messages fetch failed:", msgErr.message);
    return [];
  }

  return (msgRows ?? []).map(m => ({
    role: m.direction === "out" ? "assistant" : "user",
    content: m.body ?? "",
    timestamp: m.ts ?? undefined,
  }));
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

  // Parse whatsapp_conversations messages (if any).
  let conversationsMessages: ConversationMessage[] = [];
  let conversationsUpdatedAt: string | null = null;
  let conversationsReason: string | null = null;

  if (!row) {
    conversationsReason = "no_row";
  } else if (!ctx.isAdmin && row.client_id !== ctx.clientId) {
    // Cross-tenant safety. Treat as "no usable conversation row" and fall
    // through to maya_watch fallback (which applies its own client_id scope).
    console.warn("[/api/whatsapp-history] client_id mismatch: row=%s ctx=%s", row.client_id, ctx.clientId);
    conversationsReason = "client_mismatch";
  } else {
    conversationsUpdatedAt = row.updated_at ?? null;
    const raw = row.messages_json;
    if (Array.isArray(raw)) {
      conversationsMessages = raw as ConversationMessage[];
    } else if (typeof raw === "string") {
      try {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) conversationsMessages = parsed;
      } catch {
        conversationsMessages = [];
      }
    }
    if (conversationsMessages.length === 0) conversationsReason = "empty_messages";
  }

  if (conversationsMessages.length > 0) {
    return NextResponse.json({
      messages: conversationsMessages,
      updated_at: conversationsUpdatedAt,
    });
  }

  // Fallback — Maya Watch messages for the same phone + tenant.
  const fallback = await fetchMayaWatchHistory(admin, phone, ctxClientId);
  return NextResponse.json({
    messages: fallback,
    updated_at: null,
    debug: {
      phone,
      ctxClientId,
      isAdmin: ctx.isAdmin,
      rowsFound,
      conversationsReason,
      fallbackUsed: true,
      fallbackCount: fallback.length,
    },
  });
}
