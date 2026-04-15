import { createClient } from "@supabase/supabase-js";

/**
 * Supabase Admin client — uses service role key, bypasses RLS.
 * Use ONLY in server-side code for admin operations (user management).
 */
export function createSupabaseAdminClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
  const key = process.env.SUPABASE_SERVICE_KEY!;
  return createClient(url, key, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
}
