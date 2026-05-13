// Resolve the {name, role} rendered in the home sidebar from a Supabase
// user. Mirrors the pickString/resolveLiveIdentity logic used inside
// /home/watch — kept tiny and side-effect-free so any /home/* page can
// surface the operator's real identity instead of mock data.

import type { User } from "@supabase/supabase-js";

const PRODUCT_NAME = "Maya Watch";
const PRODUCT_ROLE = "מצב חי";

function pick(meta: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const k of keys) {
    const v = meta[k];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return undefined;
}

export function resolveHomeIdentity(user: User | null | undefined): { name: string; role: string } {
  const meta = (user?.user_metadata ?? {}) as Record<string, unknown>;
  const name = pick(meta, "name", "full_name", "display_name");
  const role = pick(meta, "business_name", "business", "company", "role");
  if (name && role) return { name, role };
  if (name)         return { name, role: PRODUCT_ROLE };
  if (role)         return { name: PRODUCT_NAME, role };
  return { name: PRODUCT_NAME, role: PRODUCT_ROLE };
}
