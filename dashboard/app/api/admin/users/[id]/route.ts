import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { createSupabaseAdminClient } from "@/lib/supabase-admin";
import { getUserContext } from "@/lib/user-context";

async function requireAdmin() {
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx?.isAdmin) return false;
  return true;
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  if (!await requireAdmin()) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const { id } = await params;
  const { role, client_id, password, disabled } = await req.json();

  const admin = createSupabaseAdminClient();

  const update: Parameters<typeof admin.auth.admin.updateUserById>[1] = {};

  if (password) update.password = password;

  if (typeof disabled === "boolean") {
    // ban_duration: '876600h' (~100 years) = effectively disabled; 'none' = enabled
    update.ban_duration = disabled ? "876600h" : "none";
  }

  if (role === "admin") {
    update.user_metadata = { role: "admin" };
  } else if (client_id) {
    update.user_metadata = { client_id };
  }

  const { data, error } = await admin.auth.admin.updateUserById(id, update);
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json(data.user);
}
