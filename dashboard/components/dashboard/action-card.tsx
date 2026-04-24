"use client";

import { useState } from "react";
import { Check, X, Pencil, MessageSquare } from "lucide-react";

export interface ActionProposal {
  action: string;
  status: string;
  lead_name: string;
  channel: string;
  message: string;
}

type CardState = "pending" | "approved" | "editing" | "cancelled";

interface Props {
  proposal: ActionProposal;
  onDismiss: () => void;
}

export function ActionCard({ proposal, onDismiss }: Props) {
  const [cardState, setCardState] = useState<CardState>("pending");
  const [editedMessage, setEditedMessage] = useState(proposal.message);

  const handleApprove = () => {
    setCardState("approved");
    // MVP: no real action — just visual confirmation
  };

  const handleEdit = () => {
    setCardState("editing");
  };

  const handleSaveEdit = () => {
    setCardState("approved");
    // MVP: saves locally only
  };

  const handleCancel = () => {
    setCardState("cancelled");
    setTimeout(onDismiss, 500);
  };

  if (cardState === "cancelled") return null;

  return (
    <div className="mt-4 rounded-xl border border-border overflow-hidden bg-surface-2/80" dir="rtl">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border/50">
        <MessageSquare className="w-4 h-4 text-brand-400" />
        <span className="text-[12px] font-medium text-white">
          הודעת follow-up — {proposal.lead_name}
        </span>
        <span className="text-[10px] text-gray-500 mr-auto">
          {proposal.channel}
        </span>
      </div>

      {/* Message body */}
      <div className="px-4 py-3">
        {cardState === "editing" ? (
          <textarea
            value={editedMessage}
            onChange={(e) => setEditedMessage(e.target.value)}
            className="w-full bg-surface-0 text-gray-200 text-[12px] rounded-lg p-2.5 border border-border/50 resize-none focus:outline-none focus:border-brand-500"
            rows={3}
          />
        ) : (
          <p className="text-gray-300 text-[12px] leading-relaxed whitespace-pre-wrap">
            {cardState === "approved" ? editedMessage : proposal.message}
          </p>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-t border-border/50">
        {cardState === "approved" ? (
          <div className="flex items-center gap-1.5 text-green-400 text-[11px]">
            <Check className="w-3.5 h-3.5" />
            <span>אושר כטיוטה</span>
          </div>
        ) : cardState === "editing" ? (
          <>
            <button
              onClick={handleSaveEdit}
              className="flex items-center gap-1 px-3 py-1.5 bg-brand-600 hover:bg-brand-500 text-white text-[11px] rounded-lg transition-colors"
            >
              <Check className="w-3 h-3" />
              שמור
            </button>
            <button
              onClick={() => setCardState("pending")}
              className="text-gray-500 hover:text-gray-300 text-[11px] px-2 py-1.5 transition-colors"
            >
              ביטול
            </button>
          </>
        ) : (
          <>
            <button
              onClick={handleApprove}
              className="flex items-center gap-1 px-3 py-1.5 bg-brand-600 hover:bg-brand-500 text-white text-[11px] rounded-lg transition-colors"
            >
              <Check className="w-3 h-3" />
              אשר
            </button>
            <button
              onClick={handleEdit}
              className="flex items-center gap-1 px-3 py-1.5 text-gray-400 hover:text-white text-[11px] rounded-lg hover:bg-surface-0 transition-colors"
            >
              <Pencil className="w-3 h-3" />
              ערוך
            </button>
            <button
              onClick={handleCancel}
              className="flex items-center gap-1 px-3 py-1.5 text-gray-500 hover:text-red-400 text-[11px] rounded-lg hover:bg-red-500/10 transition-colors"
            >
              <X className="w-3 h-3" />
              בטל
            </button>
          </>
        )}
      </div>
    </div>
  );
}
