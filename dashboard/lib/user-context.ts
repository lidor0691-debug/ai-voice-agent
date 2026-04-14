import type { User } from "@supabase/supabase-js";

export type UserContext =
  | { isAdmin: true }
  | { isAdmin: false; clientId: string };

/**
 * Extract auth context from a Supabase user.
 * Returns null if unauthenticated or no client_id.
 * Admin: user_metadata.role === "admin"
 * Client: user_metadata.client_id is a UUID string
 */
export function getUserContext(user: User | null | undefined): UserContext | null {
  if (!user) return null;
  const meta = user.user_metadata ?? {};
  if (meta.role === "admin") return { isAdmin: true };
  const clientId = meta.client_id as string | undefined;
  if (!clientId) return null;
  return { isAdmin: false, clientId };
}
