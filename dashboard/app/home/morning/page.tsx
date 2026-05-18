export const dynamic = "force-dynamic";

import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { HomeShell } from "../_shared/HomeShell";
import { HomeNavRail } from "../_shared/HomeNavRail";
import { resolveHomeIdentity } from "../_shared/identity";
import { SuggestionCard } from "./suggestion-card";
import { approveAction, skipAction, editAction } from "./actions";

// Privacy: do not select or render lead_id, phone, raw payload, raw evidence,
// or internal analysis fields. The query intentionally omits lead_id and never
// joins leads. Rendering whitelists only payload.message_he / payload_edited.message_he,
// payload.first_name, and payload.safety.template_version. No raw payload dump.

// ── Types ────────────────────────────────────────────────────────────────

type SuggestionStatus =
  | "suggested"
  | "pending_approval"
  | "edited"
  | "approved"
  | "executing"
  | "executed"
  | "failed"
  | "skipped"
  | "cancelled"
  | "expired";

interface SuggestionRow {
  id: string;
  client_id: string;
  agent_id: string | null;
  action_type: string;
  status: SuggestionStatus;
  permission_mode_at_creation: string;
  risk_level: string;
  payload: unknown;
  payload_edited: unknown;
  rationale_he: string | null;
  expires_at: string;
  created_at: string;
  updated_at: string;
  version: number;
}

// Statuses safe to render in 3.9. `approved` is intentionally NOT here:
// no executor exists yet, so surfacing it would imply imminent send.
const VISIBLE_STATUSES = ["suggested", "pending_approval", "edited"] as const;

const STATUS_LABEL_HE: Record<string, string> = {
  suggested:        "ממתין לאישור",
  pending_approval: "ממתין לאישור",
  edited:           "נערך וממתין לאישור",
};

// ── Pure helpers ─────────────────────────────────────────────────────────

function isNonEmptyString(v: unknown): v is string {
  return typeof v === "string" && v.trim().length > 0;
}

function getPayloadField(payload: unknown, key: string): unknown {
  if (!payload || typeof payload !== "object") return undefined;
  return (payload as Record<string, unknown>)[key];
}

function resolveMessageHe(row: SuggestionRow): { text: string; missing: boolean } {
  const edited = getPayloadField(row.payload_edited, "message_he");
  if (isNonEmptyString(edited)) return { text: edited.trim(), missing: false };
  const original = getPayloadField(row.payload, "message_he");
  if (isNonEmptyString(original)) return { text: original.trim(), missing: false };
  return { text: "הודעה מוכנה לא זמינה", missing: true };
}

function resolveFirstName(row: SuggestionRow): string | null {
  const fn = getPayloadField(row.payload, "first_name");
  return isNonEmptyString(fn) ? fn.trim() : null;
}

function resolveRationale(row: SuggestionRow): string {
  if (isNonEmptyString(row.rationale_he)) return row.rationale_he.trim();
  return "מאיה זיהתה שכדאי לבדוק את הליד הזה בזמן.";
}

function relativeHebrew(iso: string): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return "";
  const diffMs = ts - Date.now();
  if (diffMs <= 0) return "פג תוקף";
  const hours = diffMs / (1000 * 60 * 60);
  if (hours < 1) return "בעוד פחות משעה";
  if (hours < 24) {
    const h = Math.floor(hours);
    return h === 1 ? "בעוד שעה" : `בעוד ${h} שעות`;
  }
  const days = Math.floor(hours / 24);
  return days === 1 ? "בעוד יום" : `בעוד ${days} ימים`;
}

function permissionLabel(mode: string): string {
  if (mode === "suggest_only")     return "במצב הזה ההמלצה היא לתצוגה בלבד.";
  if (mode === "require_approval") return "נדרש אישור לפני שליחה";
  return "נדרש אישור לפני שליחה";
}

function statusLabel(status: string): string {
  return STATUS_LABEL_HE[status] ?? "ממתין לאישור";
}

function heroLine(count: number): string {
  if (count === 1) return "בוקר טוב. יש פעולה אחת שממתינה לאישור שלך.";
  return `בוקר טוב. יש ${count} פעולות שממתינות לאישור שלך.`;
}

function overflowLine(extraCount: number): string {
  if (extraCount === 1) return "ועוד פעולה אחת ממתינה";
  return `ועוד ${extraCount} פעולות ממתינות`;
}

// ── Page ─────────────────────────────────────────────────────────────────

export default async function MorningPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  const ctx = getUserContext(user);
  if (!ctx) redirect("/login");
  const identity = resolveHomeIdentity(user);

  // Admin without a client_id has no client to display. Surface a small hint
  // pointing to /admin/briefings and render no cards. We do NOT aggregate
  // across clients on /home/morning.
  //
  // getUserContext intentionally hides client_id for admins, so for the
  // admin path we peek at user.user_metadata.client_id directly. Treat
  // missing, null, undefined, and empty-string as "no client".
  const userMeta = (user.user_metadata ?? {}) as Record<string, unknown>;
  function adminClientIdFromMeta(): string | null {
    const raw = userMeta.client_id;
    if (typeof raw !== "string") return null;
    const trimmed = raw.trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  const effectiveClientId: string | null = ctx.isAdmin
    ? adminClientIdFromMeta()
    : ctx.clientId;
  const adminNoClient = ctx.isAdmin && !effectiveClientId;

  // Read-only query against maya_action_suggestions. RLS enforces scoping by
  // client_id; we additionally filter to the effective client for clarity.
  // Privacy: lead_id is intentionally NOT selected. No join to leads.
  let suggestions: SuggestionRow[] = [];
  if (effectiveClientId) {
    const nowIso = new Date().toISOString();
    const { data, error } = await supabase
      .from("maya_action_suggestions")
      .select(
        "id, client_id, agent_id, action_type, status, " +
        "permission_mode_at_creation, risk_level, " +
        "payload, payload_edited, rationale_he, " +
        "expires_at, created_at, updated_at, version",
      )
      .eq("client_id", effectiveClientId)
      .in("status", VISIBLE_STATUSES as unknown as string[])
      .gt("expires_at", nowIso)
      .order("expires_at", { ascending: true })
      .order("created_at", { ascending: false })
      .limit(4);
    if (error) console.error("[home/morning] suggestions fetch failed:", error.message);
    suggestions = (data ?? []) as unknown as SuggestionRow[];
  }

  const visible = suggestions.slice(0, 3);
  const overflowExtra = Math.max(0, suggestions.length - 3);

  return (
    <HomeShell lang="he">
      <HomeNavRail lang="he" active="watch" user={identity} />
      <div className="lg:ps-[200px] h-full overflow-y-auto overflow-x-hidden">
        <div className="max-w-3xl mx-auto px-5 sm:px-8 py-8 sm:py-12 space-y-8" dir="rtl">

          {/* Admin without client → admin hint, no cards */}
          {adminNoClient && (
            <section className="rounded-2xl border border-[#0B1714]/10 bg-white/60 px-6 py-10 text-center">
              <div className="maya-section-label mb-2">תדריך הבוקר של מאיה</div>
              <h1 className="text-[20px] font-semibold text-[#0B1714]/85 mb-2">
                אין לקוח משויך לתצוגה הזו
              </h1>
              <p className="text-[13.5px] text-[#0B1714]/60 leading-relaxed max-w-md mx-auto">
                לניהול תובנות עבור לקוחות, עבור לעמוד /admin/briefings.
              </p>
            </section>
          )}

          {/* Empty state (client with zero visible suggestions, or admin-with-client zero) */}
          {!adminNoClient && visible.length === 0 && (
            <section className="rounded-2xl border border-[#0B1714]/10 bg-white/60 px-6 py-10 text-center">
              <div className="maya-section-label mb-2">תדריך הבוקר של מאיה</div>
              <h1 className="text-[20px] font-semibold text-[#0B1714]/85 mb-2">
                אין כרגע פעולות שממתינות לאישור
              </h1>
              <p className="text-[13.5px] text-[#0B1714]/60 leading-relaxed max-w-md mx-auto">
                מאיה עדיין לא מחכה לאישור שלך. כשהיא תזהה פעולה שכדאי לאשר, היא תציג אותה כאן.
              </p>
            </section>
          )}

          {/* Hero (with suggestions) */}
          {!adminNoClient && visible.length > 0 && (
            <header>
              <div className="maya-section-label mb-2">תדריך הבוקר של מאיה</div>
              <h1 className="text-[20px] sm:text-[22px] font-semibold text-[#0B1714]/90 leading-tight">
                {heroLine(visible.length)}
              </h1>
              <p className="mt-2.5 text-[13.5px] text-[#0B1714]/60 leading-relaxed max-w-2xl">
                מאיה הכינה עבורך הודעות המשך. בשלב הזה אפשר לאשר, לערוך או לדלג על פעולות. שליחה בפועל תתווסף בשלב הבא.
              </p>
            </header>
          )}

          {/* Cards */}
          {!adminNoClient && visible.length > 0 && (
            <section className="space-y-4">
              <h2 className="text-[15px] font-semibold text-[#0B1714]/80">
                מה מחכה לאישור
              </h2>
              <div className="space-y-4">
                {visible.map(row => {
                  const { text: messageHe, missing: messageMissing } = resolveMessageHe(row);
                  const display = {
                    statusLabel:     statusLabel(row.status),
                    messageText:     messageHe,
                    messageMissing,
                    rationale:       resolveRationale(row),
                    expiryText:      relativeHebrew(row.expires_at),
                    permissionLabel: permissionLabel(row.permission_mode_at_creation),
                    firstName:       resolveFirstName(row),
                  };
                  const isReadOnly = row.permission_mode_at_creation === "suggest_only";
                  // Opaque per-render key. Suggestion id and version intentionally
                  // stay out of the client boundary; they exist only inside the
                  // bound server action closures below. A fresh UUID per render
                  // also force-remounts the client island after revalidatePath,
                  // which resets editing/skipping mode after a successful edit
                  // and avoids index-position state leakage after approve/skip.
                  const cardKey = `suggestion-card-${crypto.randomUUID()}`;
                  if (isReadOnly) {
                    return (
                      <SuggestionCard
                        key={cardKey}
                        isReadOnly={true}
                        {...display}
                      />
                    );
                  }
                  return (
                    <SuggestionCard
                      key={cardKey}
                      isReadOnly={false}
                      {...display}
                      approveAction={approveAction.bind(null, row.id, row.version)}
                      skipAction={skipAction.bind(null, row.id, row.version)}
                      editAction={editAction.bind(null, row.id, row.version)}
                    />
                  );
                })}
              </div>
              {overflowExtra > 0 && (
                <p className="text-[12.5px] text-[#0B1714]/50 pr-1">
                  {overflowLine(overflowExtra)}
                </p>
              )}
            </section>
          )}

        </div>
      </div>
    </HomeShell>
  );
}

export const metadata = { title: "Maya · תדריך הבוקר" };
