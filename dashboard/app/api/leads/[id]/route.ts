import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { createSupabaseAdminClient } from "@/lib/supabase-admin";
import { getUserContext } from "@/lib/user-context";

export const dynamic = "force-dynamic";

// Whitelist: only these fields are editable via this route.
// Phone, source, status, notes, client_id, etc. are NOT editable here.
const EDITABLE_FIELDS = ["name"] as const;

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await params;
  if (!id) return NextResponse.json({ error: "Missing id" }, { status: 400 });

  const session = await createSupabaseServerClient();
  const { data: { user } } = await session.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  let body: Record<string, unknown> = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  // Build a sanitized payload: only whitelisted fields.
  const patch: Record<string, string | null> = {};
  for (const key of EDITABLE_FIELDS) {
    if (key in body) {
      const v = body[key];
      if (v === null || v === undefined) {
        patch[key] = null;
      } else if (typeof v === "string") {
        const trimmed = v.trim();
        patch[key] = trimmed === "" ? null : trimmed;
      } else {
        return NextResponse.json({ error: `Invalid type for ${key}` }, { status: 400 });
      }
    }
  }
  if (Object.keys(patch).length === 0) {
    return NextResponse.json({ error: "No editable fields in body" }, { status: 400 });
  }

  // Use admin client to bypass RLS for the read-check + update, then enforce
  // client_id scoping in code.
  const admin = createSupabaseAdminClient();

  const { data: existing, error: readErr } = await admin
    .from("leads")
    .select("id, client_id, name, phone")
    .eq("id", id)
    .limit(1);
  if (readErr) {
    console.error("[/api/leads/:id PATCH] read error:", readErr.message);
    return NextResponse.json({ error: "Lookup failed" }, { status: 500 });
  }
  const row = (existing ?? [])[0];
  if (!row) return NextResponse.json({ error: "Not found" }, { status: 404 });

  if (!ctx.isAdmin && row.client_id !== ctx.clientId) {
    console.warn("[/api/leads/:id PATCH] forbidden: lead=%s row_client=%s ctx_client=%s", id, row.client_id, ctx.clientId);
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const { data: updated, error: updErr } = await admin
    .from("leads")
    .update(patch)
    .eq("id", id)
    .select()
    .limit(1);
  if (updErr) {
    console.error("[/api/leads/:id PATCH] update error:", updErr.message);
    return NextResponse.json({ error: "Update failed" }, { status: 500 });
  }

  return NextResponse.json({ lead: (updated ?? [])[0] ?? null });
}
