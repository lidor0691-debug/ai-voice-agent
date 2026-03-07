"use client";

import {
  X,
  Phone,
  Bot,
  Lightbulb,
  MessageSquare,
  CalendarCheck,
  CheckCircle2,
  Clock,
  Bike,
} from "lucide-react";
import { StatusBadge, BoolBadge, Badge } from "@/components/ui/badge";
import { formatDate, formatTime, addSeconds, maskPhone } from "@/lib/utils";
import type { Lead } from "@/types/lead";

const NO_APPOINTMENT = "ממתין לתיאום";

interface TimelineEvent {
  Icon: React.ComponentType<{ className?: string }>;
  label: string;
  detail: string;
  time: string;
  done: boolean;
}

function buildTimeline(lead: Lead): TimelineEvent[] {
  const t = lead.created_at;

  return [
    {
      Icon: Phone,
      label: "שיחה נכנסה",
      detail: `ממספר ${maskPhone(lead.phone)}`,
      time: formatTime(t),
      done: true,
    },
    {
      Icon: Bot,
      label: "מאיה ענתה",
      detail: "הסייעת הדיגיטלית פתחה שיחה בעברית",
      time: formatTime(addSeconds(t, 4)),
      done: true,
    },
    {
      Icon: Lightbulb,
      label: "זוהתה כוונת לקוח",
      detail: lead.intents.length > 0 ? lead.intents.join(" | ") : "—",
      time: formatTime(addSeconds(t, 90)),
      done: true,
    },
    {
      Icon: MessageSquare,
      label: "נשלח SMS",
      detail: lead.sms_sent ? "אישור קבלת הפנייה נשלח ללקוח" : "טרם נשלח",
      time: lead.sms_sent ? formatTime(addSeconds(t, 95)) : "—",
      done: lead.sms_sent,
    },
    {
      Icon: CalendarCheck,
      label: "נקבע ביומן",
      detail: lead.calendar_booked
        ? lead.appointment_time
          ? `תור: ${formatDate(lead.appointment_time)}`
          : "תור אושר"
        : NO_APPOINTMENT,
      time: lead.calendar_booked ? formatTime(addSeconds(t, 600)) : "—",
      done: lead.calendar_booked,
    },
  ];
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

  return (
    <>
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-brand-100 flex items-center justify-center text-brand-700 font-bold text-sm flex-shrink-0">
            {lead.name.charAt(0)}
          </div>
          <div>
            <p className="text-slate-900 font-semibold text-sm">{lead.name}</p>
            <p className="text-slate-400 text-xs font-mono mt-0.5">
              {maskPhone(lead.phone)}
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-2 rounded-lg hover:bg-slate-100 transition-colors text-slate-400 hover:text-slate-600"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto">
        {/* Lead details */}
        <div className="px-6 py-5 border-b border-slate-100 space-y-4">
          {/* Model */}
          <div className="flex items-start gap-3">
            <Bike className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-slate-400 text-xs">דגם</p>
              <p className="text-slate-800 text-sm font-semibold mt-0.5">
                {lead.model || "—"}
              </p>
            </div>
          </div>

          {/* Field grid */}
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            <div className="col-span-2">
              <p className="text-slate-400 text-xs">כוונות</p>
              <div className="flex flex-wrap gap-1 mt-1">
                {lead.intents.length > 0
                  ? lead.intents.map((v) => <Badge key={v} variant="default">{v}</Badge>)
                  : <span className="text-slate-400 text-sm">—</span>
                }
              </div>
            </div>

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
                <p className="text-slate-800 text-sm mt-0.5">{lead.source}</p>
              </div>
            )}

            <div>
              <p className="text-slate-400 text-xs">SMS</p>
              <div className="mt-1">
                <BoolBadge value={lead.sms_sent} labelTrue="נשלח" labelFalse="לא נשלח" />
              </div>
            </div>

            <div>
              <p className="text-slate-400 text-xs">יומן</p>
              <div className="mt-1">
                <BoolBadge value={lead.calendar_booked} labelTrue="נקבע" labelFalse="לא נקבע" />
              </div>
            </div>

            {/* appointment_time — always shown, falls back to "ממתין לתיאום" */}
            <div className="col-span-2">
              <p className="text-slate-400 text-xs">תאריך תור</p>
              <p className={`text-sm mt-0.5 font-medium ${lead.appointment_time ? "text-slate-800" : "text-slate-400"}`}>
                {lead.appointment_time ? formatDate(lead.appointment_time) : NO_APPOINTMENT}
              </p>
            </div>
          </div>

          <p className="text-slate-400 text-xs flex items-center gap-1.5 pt-1">
            <Clock className="w-3 h-3" />
            פנייה: {formatDate(lead.created_at)}
          </p>
        </div>

        {/* Timeline */}
        <div className="px-6 py-5">
          <p className="text-slate-700 font-semibold text-sm mb-5">ציר זמן השיחה</p>
          <ol className="relative border-s border-slate-200 space-y-6">
            {timeline.map((event, i) => (
              <li key={i} className="ms-6">
                <span
                  className={`absolute -start-3 flex items-center justify-center w-6 h-6 rounded-full ring-4 ring-white ${
                    event.done ? "bg-brand-500" : "bg-slate-200"
                  }`}
                >
                  {event.done ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-white" />
                  ) : (
                    <event.Icon className="w-3.5 h-3.5 text-slate-400" />
                  )}
                </span>
                <div>
                  <div className="flex items-center justify-between gap-2 mb-0.5">
                    <p className={`text-sm font-medium ${event.done ? "text-slate-900" : "text-slate-400"}`}>
                      {event.label}
                    </p>
                    <span className="text-xs text-slate-400 whitespace-nowrap">{event.time}</span>
                  </div>
                  <p className="text-xs text-slate-500">{event.detail}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>

      {/* Action footer */}
      <div className="px-6 py-4 border-t border-slate-100 flex gap-3 flex-shrink-0">
        <button className="flex-1 py-2.5 text-sm font-medium bg-brand-500 hover:bg-brand-600 text-white rounded-lg transition-colors">
          קבע תור
        </button>
        <button className="flex-1 py-2.5 text-sm font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg transition-colors">
          שלח SMS
        </button>
      </div>
    </>
  );
}
