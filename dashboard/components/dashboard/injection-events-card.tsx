"use client";

import { Zap } from "lucide-react";

interface InjectionEvent {
  created_at: string;
  new_data: { client_id: string; rule_key: string; sentence: string; weight: number };
}

interface Props {
  events: InjectionEvent[] | null;
}

export function InjectionEventsCard({ events }: Props) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-3">
        <Zap className="w-4 h-4 text-brand-400" />
        <div>
          <p className="text-white text-[13px] font-semibold">הזרקות חכמות</p>
          <p className="text-gray-600 text-[10px] mt-0.5">משפטים שנוספו לשיחות WhatsApp</p>
        </div>
      </div>

      {!events || events.length === 0 ? (
        <p className="text-gray-700 text-[11px] text-center py-3">אין הזרקות עדיין</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {events.map((ev, i) => (
            <div
              key={i}
              className="rounded-[10px] border border-border px-3 py-2 flex items-start gap-3"
              style={{ background: "rgba(255,255,255,0.02)" }}
            >
              <div className="flex flex-col gap-0.5 flex-1 min-w-0">
                <p className="text-gray-300 text-[11px] leading-snug truncate">
                  {ev.new_data?.sentence}
                </p>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ color: "#a78bfa", background: "rgba(139,92,246,0.1)" }}>
                    {ev.new_data?.rule_key}
                  </span>
                  <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ color: "#10b981", background: "rgba(16,185,129,0.08)" }}>
                    ×{ev.new_data?.weight}
                  </span>
                </div>
              </div>
              <span className="text-gray-700 text-[9px] flex-shrink-0 mt-0.5">
                {new Date(ev.created_at).toLocaleString("he-IL", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
