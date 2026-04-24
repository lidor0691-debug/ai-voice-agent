"use client";

import { useState } from "react";
import { Check, X, Pencil, MessageSquare, Send, Loader2 } from "lucide-react";

export interface ActionProposal {
  action: string;
  status: string;
  lead_name: string;
  channel: string;
  message: string;
  lead_phone?: string;
  agent_id?: string;
}

type CardState = "pending" | "editing" | "sending" | "sent" | "failed" | "cancelled";

interface Props {
  proposal: ActionProposal;
  onDismiss: () => void;
}

export function ActionCard({ proposal, onDismiss }: Props) {
  const [cardState, setCardState] = useState<CardState>("pending");
  const [editedMessage, setEditedMessage] = useState(proposal.message);
  const [sendError, setSendError] = useState("");

  const currentMessage = cardState === "pending" ? proposal.message : editedMessage;

  const handleEdit = () => {
    setCardState("editing");
  };

  const handleSaveEdit = () => {
    setCardState("pending");
  };

  const handleCancel = () => {
    setCardState("cancelled");
    setTimeout(onDismiss, 300);
  };

  const handleSend = async () => {
    setCardState("sending");
    setSendError("");

    try {
      const res = await fetch("/api/actions/send-whatsapp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phone: proposal.lead_phone || "",
          message: editedMessage || proposal.message,
          lead_name: proposal.lead_name,
          agent_id: proposal.agent_id || "",
        }),
      });

      const data = await res.json();

      if (data.status === "sent") {
        setCardState("sent");
      } else {
        setCardState("failed");
        setSendError(data.error || data.detail || "שליחה נכשלה");
      }
    } catch {
      setCardState("failed");
      setSendError("לא ניתן להתחבר לשרת");
    }
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
            {currentMessage}
          </p>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-t border-border/50">
        {cardState === "sent" ? (
          <div className="flex items-center gap-1.5 text-green-400 text-[11px]">
            <Check className="w-3.5 h-3.5" />
            <span>נשלח בהצלחה</span>
          </div>
        ) : cardState === "failed" ? (
          <div className="flex items-center gap-2 w-full">
            <span className="text-red-400 text-[11px]">{sendError}</span>
            <button
              onClick={() => setCardState("pending")}
              className="text-gray-400 hover:text-white text-[11px] px-2 py-1 mr-auto"
            >
              נסה שוב
            </button>
          </div>
        ) : cardState === "sending" ? (
          <div className="flex items-center gap-1.5 text-brand-400 text-[11px]">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            <span>שולח...</span>
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
              onClick={() => { setEditedMessage(proposal.message); setCardState("pending"); }}
              className="text-gray-500 hover:text-gray-300 text-[11px] px-2 py-1.5 transition-colors"
            >
              ביטול
            </button>
          </>
        ) : (
          <>
            <button
              onClick={handleSend}
              className="flex items-center gap-1 px-3 py-1.5 bg-green-600 hover:bg-green-500 text-white text-[11px] rounded-lg transition-colors"
            >
              <Send className="w-3 h-3" />
              שלח עכשיו
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
