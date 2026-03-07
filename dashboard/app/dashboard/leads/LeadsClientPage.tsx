"use client";

import { useState } from "react";
import { Download, SlidersHorizontal } from "lucide-react";
import { Header } from "@/components/layout/header";
import { LeadsTable } from "@/components/dashboard/leads-table";
import { computeStats } from "@/lib/utils";
import type { Lead } from "@/types/lead";

const INTENTS = ["נסיעת מבחן", "טיפול / מוסך", "יד 2", "מכירה", "הצעת מחיר"];
const STATUSES = ["ליד חדש", "בטיפול", "SMS נשלח", "תור נקבע"];

interface Props {
  initialLeads: Lead[];
}

export function LeadsClientPage({ initialLeads }: Props) {
  const [intentFilter, setIntentFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  const filtered = initialLeads.filter((l) => {
    if (intentFilter !== "all" && !l.intents.includes(intentFilter)) return false;
    if (statusFilter !== "all") {
      const effectiveStatus = l.status === "new" ? "ליד חדש" : l.status;
      if (effectiveStatus !== statusFilter) return false;
    }
    return true;
  });

  const stats = computeStats(initialLeads);

  function handleExport() {
    const headers = [
      "שם", "טלפון", "דגם", "כוונה", "ק\"מ",
      "סטטוס", "מקור", "SMS", "יומן", "תאריך תור", "תאריך פנייה",
    ];
    const rows = initialLeads.map((l) => [
      l.name,
      l.phone,
      l.model,
      l.intents.join(" | "),
      l.mileage,
      l.status,
      l.source,
      l.sms_sent ? "כן" : "לא",
      l.calendar_booked ? "כן" : "לא",
      l.appointment_time ?? "ממתין לתיאום",
      l.created_at,
    ]);
    const csv = [headers, ...rows]
      .map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "honda-leads.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <Header title="פניות" subtitle={`${stats.total} פניות בסך הכל`} />
      <main className="flex-1 overflow-y-auto p-8 space-y-5" dir="rtl">
        {/* Filter bar */}
        <div className="flex items-start gap-4 flex-wrap">
          <div className="flex items-center gap-2 text-slate-500 mt-1.5">
            <SlidersHorizontal className="w-4 h-4" />
            <span className="text-sm font-medium">סינון:</span>
          </div>

          <div>
            <p className="text-slate-400 text-xs mb-1.5">כוונה</p>
            <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-lg p-1 flex-wrap">
              <FilterButton active={intentFilter === "all"} onClick={() => setIntentFilter("all")}>הכל</FilterButton>
              {INTENTS.map((v) => (
                <FilterButton key={v} active={intentFilter === v} onClick={() => setIntentFilter(v)}>
                  {v}
                </FilterButton>
              ))}
            </div>
          </div>

          <div>
            <p className="text-slate-400 text-xs mb-1.5">סטטוס</p>
            <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-lg p-1">
              <FilterButton active={statusFilter === "all"} onClick={() => setStatusFilter("all")}>הכל</FilterButton>
              {STATUSES.map((v) => (
                <FilterButton key={v} active={statusFilter === v} onClick={() => setStatusFilter(v)}>
                  {v}
                </FilterButton>
              ))}
            </div>
          </div>

          <div className="flex-1" />

          <button
            onClick={handleExport}
            className="mt-5 flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors shadow-sm"
          >
            <Download className="w-4 h-4" />
            ייצא CSV
          </button>
        </div>

        <p className="text-sm text-slate-500">
          מציג <strong className="text-slate-900">{filtered.length}</strong>{" "}
          מתוך <strong className="text-slate-900">{stats.total}</strong> פניות
        </p>

        <LeadsTable leads={filtered} showSearch />
      </main>
    </>
  );
}

function FilterButton({
  children, active, onClick,
}: {
  children: React.ReactNode;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1 text-sm rounded-md transition-colors whitespace-nowrap ${
        active ? "bg-brand-500 text-white font-medium" : "text-slate-600 hover:bg-slate-50"
      }`}
    >
      {children}
    </button>
  );
}
