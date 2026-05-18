"use server";

import { revalidatePath } from "next/cache";
import { createSupabaseServerClient } from "@/lib/supabase-server";

export type ActionState = { ok: boolean; code?: string; message?: string };

const INITIAL_OK: ActionState = { ok: true };

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

export { INITIAL_OK as INITIAL_ACTION_STATE };
