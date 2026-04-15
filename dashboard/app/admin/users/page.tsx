export const dynamic = "force-dynamic";

import { createSupabaseAdminClient } from "@/lib/supabase-admin";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { UsersClient } from "./UsersClient";

type ClientRow = { id: string; name: string };

export default async function UsersPage() {
  const admin = createSupabaseAdminClient();
  const ssrClient = await createSupabaseServerClient();

  const [usersRes, clientsRes] = await Promise.all([
    admin.auth.admin.listUsers(),
    ssrClient.from("clients").select("id, name").order("name"),
  ]);

  const users = (usersRes.data?.users ?? []).map((u) => ({
    id: u.id,
    email: u.email ?? "",
    role: (u.user_metadata?.role as string | undefined) ?? null,
    client_id: (u.user_metadata?.client_id as string | undefined) ?? null,
    created_at: u.created_at,
    last_sign_in_at: u.last_sign_in_at ?? null,
    banned: u.banned_until != null,
  }));

  const clients = (clientsRes.data ?? []) as ClientRow[];

  return <UsersClient users={users} clients={clients} />;
}
