"use client";

import { useState, useEffect, useCallback } from "react";
import { CalendarX, MessageSquareOff, AlertTriangle, Loader2, Check } from "lucide-react";
import { ActionCard, type ActionProposal } from "@/components/dashboard/action-card";

interface Signal {
  id: string;
  created_at: string;
  lead_id: string;
  lead_phone: string;
  lead_name: string | null;
  signal_type: string;
  detail: Record<string, unknown>;
  suggested_action: string | null;
  status: string;
}

const SIGNAL_CONFIG: Record<string, { icon: typeof CalendarX; color: string; bg: string; label: string }> = {
  noshow_not_reactivated: {
    icon: CalendarX,
    color: "#ef4444",
    bg: "rgba(239,68,68,0.1)",
    label: "לא הגיע/ה לתור",
  },
  conversation_drop: {
    icon: MessageSquareOff,
    color: "#f59e0b",
    bg: "rgba(245,158,11,0.1)",
    label: "הודעה ללא מענה",
  },
};

function maskPhone(phone: string): string {
  if (phone.length < 8) return phone;
  return phone.slice(0, 4) + "••••" + phone.slice(-3);
}

function signalDescription(signal: Signal): string {
  const detail = signal.detail;
  if (signal.signal_type === "noshow_not_reactivated") {
    const appt = detail.appointment_at as string | undefined;
    if (appt) {
      try {
        const d = new Date(appt);
        const formatted = d.toLocaleDateString("he-IL", { day: "numeric", month: "numeric" })
          + " " + d.toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" });
        return `התור היה ב-${formatted} ולא בוצע מעקב`;
      } catch { /* fall through */ }
    }
    return "לא הגיע/ה לתור ולא בוצע מעקב";
  }
  if (signal.signal_type === "conversation_drop") {
    const hours = detail.hours_since as number | undefined;
    const preview = detail.last_customer_message as string | undefined;
    let text = "הלקוח/ה שלח/ה הודעה ולא קיבל/ה מענה";
    if (hours) text += ` (לפני ${hours} שעות)`;
    if (preview) text += `: "${preview.slice(0, 50)}${preview.length > 50 ? "..." : ""}"`;
    return text;
  }
  return signal.suggested_action ?? "";
}

interface Props {
  agentId?: string;
  onCountChange?: (count: number) => void;
}

export function MobilePriorities({ agentId, onCountChange }: Props) {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeProposal, setActiveProposal] = useState<ActionProposal | null>(null);

  const fetchSignals = useCallback(async () => {
    try {
      const res = await fetch("/api/action-queue");
      if (!res.ok) return;
      const data = await res.json();
      const sigs = data.signals ?? [];
      setSignals(sigs);
      onCountChange?.(sigs.length);
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, [onCountChange]);

  useEffect(() => { fetchSignals(); }, [fetchSignals]);

  const handleDismiss = async (id: string) => {
    setSignals((prev) => {
      const next = prev.filter((s) => s.id !== id);
      onCountChange?.(next.length);
      return next;
    });
    try {
      await fetch(`/api/action-queue/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "dismissed" }),
      });
    } catch { /* silent — already removed from UI */ }
  };

  const handleAct = (signal: Signal) => {
    if (!agentId) return;
    setSignals((prev) => {
      const next = prev.filter((s) => s.id !== signal.id);
      onCountChange?.(next.length);
      return next;
    });
    setActiveProposal({
      action: "whatsapp_followup",
      status: "pending",
      agent_id: agentId,
      lead_id: signal.lead_id,
      lead_name: signal.lead_name ?? maskPhone(signal.lead_phone),
      channel: "whatsapp",
      message: signal.suggested_action ?? "",
    });
    fetch(`/api/action-queue/${signal.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "acted" }),
    }).catch(() => {});
  };

  const count = signals.length;

  return (
    <div className="space-y-3" dir="rtl">
      {/* Section header */}
      <div className="flex items-center gap-2">
        <AlertTriangle className="w-4 h-4 text-brand-400" />
        <p className="text-white text-sm font-semibold">סדר עדיפויות להיום</p>
        {count > 0 && (
          <span
            className="text-[10px] font-bold px-1.5 py-0.5 rounded-full"
            style={{ color: "#ef4444", background: "rgba(239,68,68,0.15)" }}
          >
            {count}
          </span>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <div className="card flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 text-gray-500 animate-spin" />
        </div>
      )}

      {/* Empty state */}
      {!loading && count === 0 && (
        <div className="card flex items-center justify-center gap-2 py-8">
          <Check className="w-5 h-5 text-green-500" />
          <p className="text-gray-400 text-sm">אין לידים שדורשים טיפול כרגע</p>
        </div>
      )}

      {/* Signal cards */}
      {!loading && count > 0 && (
        <div className="flex flex-col gap-3">
          {signals.slice(0, 10).map((signal) => {
            const cfg = SIGNAL_CONFIG[signal.signal_type] ?? {
              icon: AlertTriangle,
              color: "#94a3b8",
              bg: "rgba(148,163,184,0.1)",
              label: signal.signal_type,
            };
            const Icon = cfg.icon;

            return (
              <div
                key={signal.id}
                className="card p-4"
              >
                {/* Type badge + lead info */}
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className="flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded"
                    style={{ color: cfg.color, background: cfg.bg }}
                  >
                    <Icon className="w-3 h-3" />
                    {cfg.label}
                  </span>
                  <span className="text-white text-sm font-medium">
                    {signal.lead_name ?? maskPhone(signal.lead_phone)}
                  </span>
                </div>

                {signal.lead_name && (
                  <p className="text-gray-600 text-xs mb-1">
                    {maskPhone(signal.lead_phone)}
                  </p>
                )}

                {/* Description */}
                <p className="text-gray-400 text-xs leading-relaxed mb-2 line-clamp-2">
                  {signalDescription(signal)}
                </p>

                {/* Suggested action */}
                {signal.suggested_action && (
                  <p className="text-gray-500 text-[11px] mb-3 flex items-start gap-1.5">
                    <span className="text-brand-400 flex-shrink-0">←</span>
                    {signal.suggested_action}
                  </p>
                )}

                {/* Action buttons — full width, touch-friendly */}
                <div className="flex gap-2">
                  <button
                    onClick={() => handleAct(signal)}
                    className="flex-1 flex items-center justify-center gap-1.5 min-h-[44px] bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium rounded-xl transition-colors"
                    disabled={!agentId}
                  >
                    טפל
                  </button>
                  <button
                    onClick={() => handleDismiss(signal.id)}
                    className="flex-1 flex items-center justify-center min-h-[44px] text-gray-400 hover:text-gray-200 text-sm rounded-xl border border-border hover:bg-surface-3 transition-colors"
                  >
                    דחה
                  </button>
                </div>
              </div>
            );
          })}
          {count > 10 && (
            <p className="text-gray-600 text-xs text-center">
              +{count - 10} נוספים
            </p>
          )}
        </div>
      )}

      {/* ActionCard overlay — same behavior as desktop */}
      {activeProposal && (
        <ActionCard
          proposal={activeProposal}
          onDismiss={() => setActiveProposal(null)}
        />
      )}
    </div>
  );
}
