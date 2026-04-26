"use client";

import { Users, Phone, AlertTriangle } from "lucide-react";

interface Props {
  activeAgents: number;
  totalCalls: number;
  openPriorities: number;
}

export function MobileKpiStrip({ activeAgents, totalCalls, openPriorities }: Props) {
  const stats = [
    { label: "סוכנים פעילים", value: activeAgents, icon: Users, color: "#a78bfa", bg: "rgba(139,92,246,0.15)" },
    { label: "שיחות", value: totalCalls, icon: Phone, color: "#10b981", bg: "rgba(16,185,129,0.12)" },
    { label: "דורש טיפול", value: openPriorities, icon: AlertTriangle, color: "#ef4444", bg: "rgba(239,68,68,0.12)" },
  ];

  return (
    <div className="grid grid-cols-3 gap-2" dir="rtl">
      {stats.map(({ label, value, icon: Icon, color, bg }) => (
        <div
          key={label}
          className="card px-3 py-2.5 flex flex-col items-center gap-1"
        >
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: bg }}
          >
            <Icon className="w-3.5 h-3.5" style={{ color }} />
          </div>
          <p className="text-white text-lg font-bold leading-none">{value}</p>
          <p className="text-gray-500 text-[9px] leading-none text-center">{label}</p>
        </div>
      ))}
    </div>
  );
}
