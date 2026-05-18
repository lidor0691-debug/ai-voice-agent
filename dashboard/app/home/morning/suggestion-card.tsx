"use client";

import { useActionState, useState } from "react";
import type { ActionState } from "./actions";

type BoundAction = (prevState: ActionState, formData: FormData) => Promise<ActionState>;

const INITIAL: ActionState = { ok: true };

const SKIP_CHIPS = [
  "לא רלוונטי עוד",
  "טופל כבר",
  "מנוסח באיכות נמוכה",
  "אחר",
] as const;
type SkipChip = typeof SKIP_CHIPS[number];

const MAX_MESSAGE_LEN = 2000;
const MAX_OTHER_LEN = 200;

type DisplayProps = {
  statusLabel: string;
  messageText: string;
  messageMissing: boolean;
  rationale: string;
  expiryText: string;
  permissionLabel: string;
  firstName: string | null;
};

export type SuggestionCardProps = DisplayProps & (
  | { isReadOnly: true }
  | {
      isReadOnly: false;
      approveAction: BoundAction;
      skipAction: BoundAction;
      editAction: BoundAction;
    }
);

// ── Wrapper (hookless) ───────────────────────────────────────────────────

export function SuggestionCard(props: SuggestionCardProps) {
  if (props.isReadOnly) {
    const { isReadOnly: _ro, ...display } = props;
    void _ro;
    return <ReadOnlySuggestionCard {...display} />;
  }
  const { isReadOnly: _ro, approveAction, skipAction, editAction, ...display } = props;
  void _ro;
  return (
    <ActionableSuggestionCard
      {...display}
      approveAction={approveAction}
      skipAction={skipAction}
      editAction={editAction}
    />
  );
}

// ── Read-only card (zero hooks) ──────────────────────────────────────────

export function ReadOnlySuggestionCard(props: DisplayProps) {
  return (
    <CardShell
      statusLabel={props.statusLabel}
      firstName={props.firstName}
      messageText={props.messageText}
      messageMissing={props.messageMissing}
      rationale={props.rationale}
      expiryText={props.expiryText}
      permissionLabel={props.permissionLabel}
    >
      <p className="mt-4 text-[12.5px] text-[#0B1714]/55">
        במצב הזה ההמלצה היא לתצוגה בלבד.
      </p>
    </CardShell>
  );
}

// ── Actionable card (all hooks top-level, unconditional) ─────────────────

type ActionableProps = DisplayProps & {
  approveAction: BoundAction;
  skipAction: BoundAction;
  editAction: BoundAction;
};

export function ActionableSuggestionCard(props: ActionableProps) {
  // Hook calls: all three, at the top, in fixed order, unconditional.
  const [approveState, runApprove, approvePending] = useActionState(props.approveAction, INITIAL);
  const [skipState, runSkip, skipPending] = useActionState(props.skipAction, INITIAL);
  const [editState, runEdit, editPending] = useActionState(props.editAction, INITIAL);

  const [mode, setMode] = useState<"default" | "editing" | "skipping">("default");
  const [draftMessage, setDraftMessage] = useState<string>(props.messageText);
  const [selectedChip, setSelectedChip] = useState<SkipChip | null>(null);
  const [otherText, setOtherText] = useState<string>("");

  function openEdit() {
    setDraftMessage(props.messageText);
    setMode("editing");
  }
  function openSkip() {
    setSelectedChip(null);
    setOtherText("");
    setMode("skipping");
  }
  function cancelToDefault() {
    setMode("default");
  }

  const skipReasonResolved: string = selectedChip === "אחר"
    ? otherText.trim()
    : selectedChip ?? "";

  const skipSubmitDisabled = skipPending || skipReasonResolved.length === 0;

  return (
    <CardShell
      statusLabel={props.statusLabel}
      firstName={props.firstName}
      messageText={mode === "editing" ? undefined : props.messageText}
      messageMissing={mode === "editing" ? false : props.messageMissing}
      rationale={props.rationale}
      expiryText={props.expiryText}
      permissionLabel={props.permissionLabel}
    >
      {/* Inline edit panel */}
      {mode === "editing" && (
        <form action={runEdit} className="mt-4 space-y-2">
          <div className="text-[11px] uppercase tracking-wider text-[#0B1714]/45 mb-1.5">
            עריכת הודעה
          </div>
          {editState.ok === false && (
            <ErrorBanner code={editState.code} message={editState.message} />
          )}
          <textarea
            name="message_he"
            dir="rtl"
            value={draftMessage}
            onChange={(e) => setDraftMessage(e.target.value)}
            rows={5}
            maxLength={MAX_MESSAGE_LEN}
            className="w-full rounded-lg border border-[#0B1714]/15 bg-white px-3 py-2 text-[13.5px] leading-relaxed text-[#0B1714]/90 focus:outline-none focus:border-[#0B1714]/35"
          />
          <div className="flex items-center justify-between gap-3">
            <span className="text-[11px] text-[#0B1714]/45">
              {draftMessage.length} / {MAX_MESSAGE_LEN}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={cancelToDefault}
                disabled={editPending}
                className="text-[12.5px] text-[#0B1714]/55 hover:text-[#0B1714]/80 disabled:opacity-50 px-2 py-1"
              >
                ביטול
              </button>
              <button
                type="submit"
                disabled={editPending || draftMessage.trim().length === 0}
                className="text-[12.5px] text-white bg-[#0B1714]/85 hover:bg-[#0B1714] disabled:opacity-50 rounded-md px-3 py-1.5"
              >
                שמור
              </button>
            </div>
          </div>
        </form>
      )}

      {/* Inline skip panel */}
      {mode === "skipping" && (
        <form action={runSkip} className="mt-4 space-y-2.5">
          <div className="text-[11px] uppercase tracking-wider text-[#0B1714]/45 mb-1.5">
            סיבת הדילוג
          </div>
          {skipState.ok === false && (
            <ErrorBanner code={skipState.code} message={skipState.message} />
          )}
          <div className="flex flex-wrap gap-1.5">
            {SKIP_CHIPS.map((chip) => {
              const active = selectedChip === chip;
              return (
                <button
                  key={chip}
                  type="button"
                  onClick={() => {
                    setSelectedChip(chip);
                    if (chip !== "אחר") setOtherText("");
                  }}
                  className={[
                    "text-[12px] rounded-full px-2.5 py-1 border transition-colors",
                    active
                      ? "bg-[#0B1714]/85 text-white border-[#0B1714]/85"
                      : "bg-white text-[#0B1714]/70 border-[#0B1714]/15 hover:border-[#0B1714]/35",
                  ].join(" ")}
                >
                  {chip}
                </button>
              );
            })}
          </div>
          {selectedChip === "אחר" && (
            <input
              type="text"
              dir="rtl"
              value={otherText}
              onChange={(e) => setOtherText(e.target.value)}
              maxLength={MAX_OTHER_LEN}
              placeholder="פרטו בקצרה"
              className="w-full rounded-lg border border-[#0B1714]/15 bg-white px-3 py-2 text-[13px] text-[#0B1714]/90 focus:outline-none focus:border-[#0B1714]/35"
            />
          )}
          {/* Hidden carrier so the form posts the resolved reason via FormData.skip_reason only */}
          <input type="hidden" name="skip_reason" value={skipReasonResolved} />
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={cancelToDefault}
              disabled={skipPending}
              className="text-[12.5px] text-[#0B1714]/55 hover:text-[#0B1714]/80 disabled:opacity-50 px-2 py-1"
            >
              ביטול
            </button>
            <button
              type="submit"
              disabled={skipSubmitDisabled}
              className="text-[12.5px] text-white bg-[#0B1714]/85 hover:bg-[#0B1714] disabled:opacity-50 rounded-md px-3 py-1.5"
            >
              אשר דילוג
            </button>
          </div>
        </form>
      )}

      {/* Default action row */}
      {mode === "default" && (
        <div className="mt-4 space-y-2">
          {approveState.ok === false && (
            <ErrorBanner code={approveState.code} message={approveState.message} />
          )}
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={openSkip}
              className="text-[12.5px] text-[#0B1714]/65 hover:text-[#0B1714]/90 px-2 py-1"
            >
              דלג
            </button>
            <button
              type="button"
              onClick={openEdit}
              className="text-[12.5px] text-[#0B1714]/80 border border-[#0B1714]/15 hover:border-[#0B1714]/35 rounded-md px-3 py-1.5"
            >
              ערוך
            </button>
            <form action={runApprove}>
              <button
                type="submit"
                disabled={approvePending}
                className="text-[12.5px] text-white bg-[#0B1714]/85 hover:bg-[#0B1714] disabled:opacity-50 rounded-md px-3 py-1.5"
              >
                אשר
              </button>
            </form>
          </div>
        </div>
      )}
    </CardShell>
  );
}

// ── Shared shell ─────────────────────────────────────────────────────────

type CardShellProps = {
  statusLabel: string;
  firstName: string | null;
  messageText: string | undefined;
  messageMissing: boolean;
  rationale: string;
  expiryText: string;
  permissionLabel: string;
  children?: React.ReactNode;
};

function CardShell(props: CardShellProps) {
  return (
    <article className="rounded-2xl border border-[#0B1714]/10 bg-white/75 px-5 sm:px-6 py-5 shadow-[0_1px_2px_rgba(11,23,20,0.04)]">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <h3 className="text-[16px] font-semibold text-[#0B1714]/90 leading-snug">
          {props.firstName
            ? `פעולה שממתינה לאישור · ${props.firstName}`
            : "פעולה שממתינה לאישור"}
        </h3>
        <span className="inline-flex items-center text-[11px] text-[#0B1714]/70 bg-[#0B1714]/[0.05] border border-[#0B1714]/10 rounded-full px-2 py-0.5">
          {props.statusLabel}
        </span>
      </div>

      {props.messageText !== undefined && (
        <div className="mt-4">
          <div className="text-[11px] uppercase tracking-wider text-[#0B1714]/45 mb-1.5">
            הודעה שמאיה הכינה
          </div>
          <div
            className={[
              "rounded-lg border px-3.5 py-2.5 text-[13.5px] leading-relaxed whitespace-pre-wrap",
              props.messageMissing
                ? "border-[#0B1714]/10 bg-[#0B1714]/[0.02] text-[#0B1714]/45 italic"
                : "border-[#0B1714]/10 bg-[#FAF6EE]/80 text-[#0B1714]/85",
            ].join(" ")}
          >
            {props.messageText}
          </div>
        </div>
      )}

      <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-[#0B1714]/45 mb-1">למה מאיה מציעה את זה</div>
          <div className="text-[13px] text-[#0B1714]/75 leading-relaxed">{props.rationale}</div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wider text-[#0B1714]/45 mb-1">תוקף ההצעה</div>
          <div className="text-[13px] text-[#0B1714]/75">{props.expiryText}</div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wider text-[#0B1714]/45 mb-1">מצב פעולה</div>
          <div className="text-[13px] text-[#0B1714]/75">{props.permissionLabel}</div>
        </div>
      </div>

      {props.children}
    </article>
  );
}

// ── Error banner ─────────────────────────────────────────────────────────

const ERROR_COPY_HE: Record<string, string> = {
  stale_version: "הכרטיס עודכן במקום אחר. רעננו ונסו שוב.",
  expired: "ההצעה פגה. רעננו את הדף.",
  already_acted: "הצעה זו כבר טופלה.",
  wrong_status: "הצעה זו כבר טופלה.",
  invalid_status: "הצעה זו כבר טופלה.",
  invalid_payload: "הקלט אינו תקין. בדקו את ההודעה ונסו שוב.",
  forbidden: "אין הרשאה לבצע את הפעולה הזו.",
  not_found: "הכרטיס לא נמצא. רעננו את הדף.",
  not_authenticated: "יש להתחבר מחדש.",
  validation_failed_length: "ההודעה חייבת להיות באורך 1 עד 2000 תווים.",
  validation_failed_placeholder: "אין להשתמש במחזיקי מקום בסוגריים מרובעים.",
  validation_failed_currency: "אין לציין סכומי כסף בהודעה.",
  validation_failed_control_chars: "ההודעה מכילה תווי בקרה שאינם מותרים.",
  skip_reason_required: "בחרו סיבה לדילוג.",
};

const UNKNOWN_COPY_HE = "הפעולה נכשלה. נסו שוב.";

function ErrorBanner({ code, message }: { code?: string; message?: string }) {
  // For invalid_payload, the SQL validator returns a precise Hebrew reason in
  // `error_he` (forwarded as `message`). Prefer the server's specific copy
  // over the generic fallback in that case.
  const preferServerMessage = code === "invalid_payload" && typeof message === "string" && message.length > 0;
  const text = preferServerMessage
    ? (message as string)
    : (code && ERROR_COPY_HE[code]) || UNKNOWN_COPY_HE;
  return (
    <div
      role="alert"
      className="rounded-md border border-red-200 bg-red-50/70 text-[12.5px] text-red-800 px-3 py-1.5"
    >
      {text}
    </div>
  );
}
