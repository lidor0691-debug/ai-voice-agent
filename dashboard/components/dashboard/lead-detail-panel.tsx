"use client";

import { useEffect, useState } from "react";
import {
  X,
  Phone,
  Bot,
  Lightbulb,
  MessageSquare,
  CalendarCheck,
  Clock,
  Bike,
  ExternalLink,
} from "lucide-react";
import { StatusBadge, Badge } from "@/components/ui/badge";
import { formatDate, formatTime, addSeconds, displayPhone, displayLeadName, waMeLink } from "@/lib/utils";
import type { Lead } from "@/types/lead";

interface ConversationMessage {
  role: string;
  content: string;
  timestamp?: string;
}

interface TimelineEvent {
  Icon: React.ComponentType<{ className?: string }>;
  label: string;
  detail: string;
  time: string;
}

function buildTimeline(lead: Lead): TimelineEvent[] {
  const t = lead.created_at;
  const isVoice = lead.source === "voice";
  const phoneStr = displayPhone(lead.phone);

  const events: TimelineEvent[] = [
    {
      Icon: isVoice ? Phone : MessageSquare,
      label: isVoice ? "שיחה נכנסה" : "פנייה התקבלה",
      detail: phoneStr === "לא זמין" ? "" : `ממספר ${phoneStr}`,
      time: formatTime(t),
    },
    {
      Icon: Bot,
      label: "מאיה הגיבה",
      detail: isVoice
        ? "הסייעת הדיגיטלית פתחה שיחה בעברית"
        : "הסייעת הדיגיטלית השיבה בוואטסאפ",
      time: formatTime(addSeconds(t, 4)),
    },
  ];

  if (lead.intents.length > 0) {
    events.push({
      Icon: Lightbulb,
      label: "זוהתה כוונת לקוח",
      detail: lead.intents.join(" | "),
      time: formatTime(addSeconds(t, 90)),
    });
  }

  if (lead.calendar_booked) {
    events.push({
      Icon: CalendarCheck,
      label: "נקבע ביומן",
      detail: lead.appointment_time ? `תור: ${formatDate(lead.appointment_time)}` : "תור אושר",
      time: formatTime(addSeconds(t, 600)),
    });
  }

  return events;
}

interface LeadDetailPanelProps {
  lead: Lead | null;
  onClose: () => void;
}

export function LeadDetailPanel({ lead, onClose }: LeadDetailPanelProps) {
  const isOpen = lead !== null;

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        className={`fixed inset-0 bg-black/30 backdrop-blur-[2px] z-40 transition-opacity duration-300 ${
          isOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
      />

      {/* Panel — anchored to start (right in RTL), slides off to the right when closed */}
      <div
        className={`fixed top-0 start-0 h-full w-full max-w-md bg-white shadow-2xl z-50 flex flex-col transition-transform duration-300 ease-out ${
          isOpen ? "translate-x-0" : "translate-x-full"
        }`}
        dir="rtl"
      >
        {lead && <PanelContent lead={lead} onClose={onClose} />}
      </div>
    </>
  );
}

function PanelContent({ lead, onClose }: { lead: Lead; onClose: () => void }) {
  const timeline = buildTimeline(lead);
  const phoneStr = displayPhone(lead.phone);
  const nameStr = displayLeadName(lead.name);
  const hasModel = lead.model && lead.model.trim() !== "" && lead.model !== "—";
  const hasIntents = lead.intents.length > 0;
  const sourceLabel = lead.source === "voice" ? "שיחה קולית" : lead.source === "whatsapp" ? "וואטסאפ" : lead.source;
  const initial = (lead.name && lead.name.trim()) ? lead.name.trim().charAt(0) : "?";
  const waUrl = waMeLink(lead.phone);

  // Summary fields written by voice pipeline (optional, may be absent).
  const summaryParts = [
    lead.last_call_topic,
    lead.last_call_summary,
    lead.notes,
  ].filter((s): s is string => Boolean(s && s.trim()));
  const hasSummary = summaryParts.length > 0;

  // WhatsApp history — fetched for ANY lead with a valid phone, scoped server-side by client_id.
  // A customer may have called by voice but also exchanged WhatsApp messages — we want to surface
  // that history regardless of which channel created the lead row.
  const [waMessages, setWaMessages] = useState<ConversationMessage[]>([]);
  const [waLoading, setWaLoading] = useState(false);
  useEffect(() => {
    if (phoneStr === "לא זמין") {
      setWaMessages([]);
      return;
    }
    let cancelled = false;
    setWaLoading(true);
    fetch(`/api/whatsapp-history?phone=${encodeURIComponent(lead.phone)}`)
      .then((r) => (r.ok ? r.json() : { messages: [] }))
      .then((data) => {
        if (cancelled) return;
        const msgs = Array.isArray(data?.messages) ? data.messages : [];
        setWaMessages(msgs);
      })
      .catch(() => { if (!cancelled) setWaMessages([]); })
      .finally(() => { if (!cancelled) setWaLoading(false); });
    return () => { cancelled = true; };
  }, [lead.id, lead.phone, phoneStr]);

  const recentWa = waMessages.slice(-10);

  return (
    <>
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 rounded-full bg-brand-100 flex items-center justify-center text-brand-700 font-bold text-sm flex-shrink-0">
            {initial}
          </div>
          <div className="min-w-0">
            <p className="text-slate-900 font-semibold text-sm truncate">{nameStr}</p>
            <p className="text-slate-400 text-xs font-mono mt-0.5 truncate">
              {phoneStr}
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-2 rounded-lg hover:bg-slate-100 transition-colors text-slate-400 hover:text-slate-600 flex-shrink-0"
          aria-label="סגור"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto">
        {/* Lead details */}
        <div className="px-6 py-5 border-b border-slate-100 space-y-4">
          {hasModel && (
            <div className="flex items-start gap-3">
              <Bike className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-slate-400 text-xs">דגם</p>
                <p className="text-slate-800 text-sm font-semibold mt-0.5">{lead.model}</p>
              </div>
            </div>
          )}

          {/* Field grid */}
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            {hasIntents && (
              <div className="col-span-2">
                <p className="text-slate-400 text-xs">כוונות</p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {lead.intents.map((v) => <Badge key={v} variant="default">{v}</Badge>)}
                </div>
              </div>
            )}

            {lead.mileage && (
              <div>
                <p className="text-slate-400 text-xs">קילומטרים</p>
                <p className="text-slate-800 text-sm mt-0.5">{lead.mileage}</p>
              </div>
            )}

            <div>
              <p className="text-slate-400 text-xs">סטטוס</p>
              <div className="mt-1">
                <StatusBadge status={lead.status} />
              </div>
            </div>

            {lead.source && (
              <div>
                <p className="text-slate-400 text-xs">מקור</p>
                <p className="text-slate-800 text-sm mt-0.5">{sourceLabel}</p>
              </div>
            )}

            {lead.calendar_booked && lead.appointment_time && (
              <div className="col-span-2">
                <p className="text-slate-400 text-xs">תאריך תור</p>
                <p className="text-sm mt-0.5 font-medium text-slate-800">
                  {formatDate(lead.appointment_time)}
                </p>
              </div>
            )}
          </div>

          <p className="text-slate-400 text-xs flex items-center gap-1.5 pt-1">
            <Clock className="w-3 h-3" />
            פנייה: {formatDate(lead.created_at)}
          </p>
        </div>

        {/* What the customer asked — voice summary (only if present) */}
        {hasSummary && (
          <div className="px-6 py-5 border-b border-slate-100">
            <p className="text-slate-700 font-semibold text-sm mb-3">מה הלקוחה ביקשה</p>
            <div className="space-y-2">
              {summaryParts.map((part, i) => (
                <p key={i} className="text-slate-700 text-sm leading-relaxed whitespace-pre-wrap">
                  {part}
                </p>
              ))}
            </div>
          </div>
        )}

        {/* WhatsApp conversation — shown for any lead with messages on this phone, scoped by client_id server-side */}
        {(waLoading || recentWa.length > 0) && (
          <div className="px-6 py-5 border-b border-slate-100">
            <p className="text-slate-700 font-semibold text-sm mb-3">שיחת וואטסאפ</p>
            {waLoading && recentWa.length === 0 ? (
              <p className="text-slate-400 text-xs">טוען…</p>
            ) : (
              <div className="space-y-2">
                {recentWa.map((m, i) => {
                  const isCustomer = m.role === "user";
                  return (
                    <div
                      key={i}
                      className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-snug ${
                        isCustomer
                          ? "bg-slate-100 text-slate-800 me-auto rounded-bs-sm"
                          : "bg-brand-500/10 text-slate-800 ms-auto rounded-be-sm"
                      }`}
                    >
                      <p className="text-[10px] font-semibold mb-0.5 text-slate-500">
                        {isCustomer ? "לקוחה" : "מאיה"}
                      </p>
                      <p className="whitespace-pre-wrap break-words">{m.content}</p>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Timeline */}
        <div className="px-6 py-5">
          <p className="text-slate-700 font-semibold text-sm mb-5">ציר זמן הפנייה</p>
          <ol className="relative border-s border-slate-200 space-y-6">
            {timeline.map((event, i) => (
              <li key={i} className="ms-6">
                <span className="absolute -start-3 flex items-center justify-center w-6 h-6 rounded-full ring-4 ring-white bg-brand-500">
                  <event.Icon className="w-3.5 h-3.5 text-white" />
                </span>
                <div>
                  <div className="flex items-center justify-between gap-2 mb-0.5">
                    <p className="text-sm font-medium text-slate-900">{event.label}</p>
                    <span className="text-xs text-slate-400 whitespace-nowrap">{event.time}</span>
                  </div>
                  {event.detail && <p className="text-xs text-slate-500">{event.detail}</p>}
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>

      {/* Footer action — only safe option for today: open WhatsApp manually */}
      {waUrl && (
        <div className="px-6 py-4 border-t border-slate-100 flex-shrink-0">
          <a
            href={waUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-2 w-full py-2.5 text-sm font-medium bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg transition-colors"
          >
            <ExternalLink className="w-4 h-4" />
            פתח בוואטסאפ
          </a>
        </div>
      )}
    </>
  );
}
