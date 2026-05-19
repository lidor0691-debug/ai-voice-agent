"use server";

import { revalidatePath } from "next/cache";
import { createSupabaseServerClient } from "@/lib/supabase-server";

export type ActionState = { ok: boolean; code?: string; message?: string };

type RpcEnvelope = {
  ok?: boolean;
  error_code?: string | null;
  error_he?: string | null;
};

function isRpcEnvelope(v: unknown): v is RpcEnvelope {
  return !!v && typeof v === "object";
}

function mapPostgrestStatus(status: number | undefined): string {
  if (status === 401) return "not_authenticated";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  return "unknown";
}

function getFormString(formData: FormData, key: string): string | null {
  const raw = formData.get(key);
  if (typeof raw !== "string") return null;
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export async function approveAction(
  suggestionId: string,
  expectedVersion: number,
  _prevState: ActionState,
  _formData: FormData,
): Promise<ActionState> {
  const supabase = await createSupabaseServerClient();
  const { data, error, status } = await supabase.rpc("approve_action", {
    p_suggestion_id: suggestionId,
    p_expected_version: expectedVersion,
  });

  if (error) {
    return { ok: false, code: mapPostgrestStatus(status), message: error.message };
  }

  if (!isRpcEnvelope(data) || data.ok !== true) {
    const code = (isRpcEnvelope(data) && data.error_code) || "unknown";
    const message = (isRpcEnvelope(data) && data.error_he) || undefined;
    return { ok: false, code: code, message: message ?? undefined };
  }

  revalidatePath("/home/morning");
  return { ok: true };
}

export async function skipAction(
  suggestionId: string,
  expectedVersion: number,
  _prevState: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const reason = getFormString(formData, "skip_reason");
  if (!reason) {
    return { ok: false, code: "skip_reason_required" };
  }

  const supabase = await createSupabaseServerClient();
  const { data, error, status } = await supabase.rpc("skip_action", {
    p_suggestion_id: suggestionId,
    p_expected_version: expectedVersion,
    p_reason: reason,
  });

  if (error) {
    return { ok: false, code: mapPostgrestStatus(status), message: error.message };
  }

  if (!isRpcEnvelope(data) || data.ok !== true) {
    const code = (isRpcEnvelope(data) && data.error_code) || "unknown";
    const message = (isRpcEnvelope(data) && data.error_he) || undefined;
    return { ok: false, code: code, message: message ?? undefined };
  }

  revalidatePath("/home/morning");
  return { ok: true };
}

export async function editAction(
  suggestionId: string,
  expectedVersion: number,
  _prevState: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const messageHe = getFormString(formData, "message_he");
  if (!messageHe) {
    return { ok: false, code: "validation_failed_length" };
  }

  const supabase = await createSupabaseServerClient();
  const { data, error, status } = await supabase.rpc("edit_action_payload", {
    p_suggestion_id: suggestionId,
    p_expected_version: expectedVersion,
    p_message_he: messageHe,
  });

  if (error) {
    return { ok: false, code: mapPostgrestStatus(status), message: error.message };
  }

  if (!isRpcEnvelope(data) || data.ok !== true) {
    const code = (isRpcEnvelope(data) && data.error_code) || "unknown";
    const message = (isRpcEnvelope(data) && data.error_he) || undefined;
    return { ok: false, code: code, message: message ?? undefined };
  }

  revalidatePath("/home/morning");
  return { ok: true };
}

// ── sendAction ────────────────────────────────────────────────────────────
// Phase 3.11C-7. Orchestrates the user-facing send pipeline:
//   1. Refresh session + read access_token.
//   2. If the row is not yet approved, call approve_action; capture the
//      bumped version from its response envelope.
//   3. POST the (now-approved) suggestion id to the backend executor route
//      `${API_BASE_URL}/maya-actions/{id}/execute` with Bearer auth.
//   4. revalidatePath on success and on any backend Class A failure that
//      transitioned the row to terminal state in the DB.

type CardStatus = "suggested" | "pending_approval" | "edited" | "approved";

type ApproveEnvelopeWithVersion = RpcEnvelope & {
  suggestion?: { version?: number } | null;
};

const CLASS_A_CODES = new Set<string>([
  "expired",
  "permission_drift",
  "missing_phone",
  "invalid_message",
  "session_expired",
  "twilio_error",
  "config_missing",
]);

function isClassA(code: string | undefined): boolean {
  return !!code && CLASS_A_CODES.has(code);
}

export async function sendAction(
  suggestionId: string,
  cardVersion: number,
  cardStatus: CardStatus,
  _prevState: ActionState,
  _formData: FormData,
): Promise<ActionState> {
  // 1. Backend URL — never hardcoded, never NEXT_PUBLIC.
  const apiBase = (process.env.API_BASE_URL || "").trim();
  if (!apiBase) {
    return {
      ok: false,
      code: "config_missing",
      message: "API_BASE_URL לא מוגדר בשרת.",
    };
  }

  // 2. Refresh + read session.
  const supabase = await createSupabaseServerClient();
  await supabase.auth.getUser(); // triggers SSR-helper auto-refresh
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const accessToken = session?.access_token;
  if (!accessToken) {
    return { ok: false, code: "not_authenticated" };
  }

  // 3. Determine executeVersion. May require a pre-flight approve_action.
  let executeVersion: number;
  if (
    cardStatus === "suggested" ||
    cardStatus === "pending_approval" ||
    cardStatus === "edited"
  ) {
    const { data, error, status } = await supabase.rpc("approve_action", {
      p_suggestion_id: suggestionId,
      p_expected_version: cardVersion,
    });
    if (error) {
      return {
        ok: false,
        code: mapPostgrestStatus(status),
        message: error.message,
      };
    }
    if (!isRpcEnvelope(data) || data.ok !== true) {
      const code = (isRpcEnvelope(data) && data.error_code) || "unknown";
      const message = (isRpcEnvelope(data) && data.error_he) || undefined;
      // approve_action's `expired` branch transitions the suggestion to
      // 'expired' atomically; revalidate so the UI reflects the change.
      if (code === "expired") {
        revalidatePath("/home/morning");
      }
      return { ok: false, code, message: message ?? undefined };
    }
    const env = data as ApproveEnvelopeWithVersion;
    const newVersion = env.suggestion?.version;
    if (typeof newVersion !== "number") {
      // Defensive: contract requires version. Refuse to forward stale.
      return { ok: false, code: "unknown" };
    }
    executeVersion = newVersion;
  } else if (cardStatus === "approved") {
    executeVersion = cardVersion;
  } else {
    return { ok: false, code: "invalid_status" };
  }

  // 4. Call the backend executor route. JWT used once in Authorization.
  let resp: Response;
  try {
    resp = await fetch(
      `${apiBase}/maya-actions/${encodeURIComponent(suggestionId)}/execute`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ expected_version: executeVersion }),
        cache: "no-store",
      },
    );
  } catch {
    return {
      ok: false,
      code: "supabase_rpc_network_error",
      message: "לא ניתן להתחבר לשרת.",
    };
  }

  // 5. Parse envelope. FastAPI's HTTPException(detail=envelope) wraps the
  // envelope under `detail`; success bodies are direct envelopes.
  let body: unknown;
  try {
    body = await resp.json();
  } catch {
    return {
      ok: false,
      code: "supabase_rpc_network_error",
      message: "תשובה לא תקינה מהשרת.",
    };
  }

  const envelope: RpcEnvelope =
    isRpcEnvelope(body) && "ok" in body
      ? body
      : isRpcEnvelope((body as { detail?: unknown })?.detail)
      ? ((body as { detail: RpcEnvelope }).detail)
      : {};

  if (resp.ok && envelope.ok === true) {
    revalidatePath("/home/morning");
    return { ok: true };
  }

  const code = envelope.error_code || "unknown";
  const message = envelope.error_he || undefined;
  if (isClassA(code)) {
    revalidatePath("/home/morning");
  }
  return { ok: false, code, message: message ?? undefined };
}
