import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { actDecision } from "@/app/home/watch/maya-watch-api";

/**
 * POST /api/home/watch/decisions/{decisionId}/act
 *
 * Browser → this route handler → Railway. The browser never holds the
 * MAYA_WATCH_INTERNAL_KEY; this server-side handler reads it from
 * process.env and forwards to Railway with the correct headers.
 *
 * Tenant scope is derived from the authenticated Supabase user via
 * getUserContext — the browser cannot supply a client_id, even tampered
 * with, so cross-tenant action injection is structurally prevented.
 *
 * Returns Railway's response body verbatim (with its status code) so the
 * browser sees a consistent { ok, action_id, decision_id, lead_id,
 * decision_status, already_acted } shape on success and { detail: "..." }
 * on error.
 */
export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ decisionId: string }> },
) {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }
  const ctx = getUserContext(user);
  if (!ctx) {
    return NextResponse.json({ error: "unconfigured" }, { status: 403 });
  }

  const { decisionId } = await params;
  if (!decisionId) {
    return NextResponse.json({ error: "missing decision_id" }, { status: 400 });
  }

  // Tenant scope from session ONLY. A client user always passes their own
  // clientId; an admin caller passes none (admin/aggregated mode). Any
  // client_id query string from the browser is intentionally ignored.
  const clientId = ctx.isAdmin ? undefined : ctx.clientId;

  const result = await actDecision(decisionId, {
    clientId,
    actedBy: user.id,
  });

  // Pass through upstream status; if the upstream call itself failed
  // (status 0), surface as 502 so the client error path lights up.
  return NextResponse.json(result.body, { status: result.status || 502 });
}
