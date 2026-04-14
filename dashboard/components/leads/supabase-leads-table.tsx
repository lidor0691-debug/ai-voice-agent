"use client";

import { useState } from "react";
import { Search, Phone, MessageSquare } from "lucide-react";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { LeadDetailPanel } from "@/components/dashboard/lead-detail-panel";
import { formatDate } from "@/lib/utils";
import type { SupabaseLead } from "@/types/lead";

const STATUS_STYLES: Record<string, string> = {
  new:       "bg-yellow-100 text-yellow-800",
  contacted: "bg-blue-100 text-blue-800",
  scheduled: "bg-purple-100 text-purple-800",
  closed:    "bg-slate-100 text-slate-600",
};

const STATUS_LABELS: Record<string, string> = {
  new:       "חדש",
  contacted: "בטיפול",
  scheduled: "תור נקבע",
  closed:    "סגור",
};

const COLUMNS = ["שם", "טלפון", "מקור", "שירות", "סטטוס", "תאריך"];

interface Props {
  leads: SupabaseLead[];
}

export function SupabaseLeadsTable({ leads }: Props) {
  const [query, setQuery] = useState("");
  const [selectedLead, setSelectedLead] = useState<SupabaseLead | null>(null);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 50;

  const filtered = leads.filter((l) => {
    if (!query) return true;
    const q = query.toLowerCase();
    return (
      (l.name ?? "").toLowerCase().includes(q) ||
      l.phone.includes(q)
    );
  });

  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);

  // Adapt SupabaseLead to the shape LeadDetailPanel expects
  const adaptedLead = selectedLead
    ? {
        id: selectedLead.id,
        name: selectedLead.name ?? "—",
        phone: selectedLead.phone,
        model: selectedLead.service ?? "—",
        intents: [],
        mileage: "",
        appointment_time: null,
        created_at: selectedLead.created_at,
        status: selectedLead.status,
        source: selectedLead.source,
        sms_sent: false,
        calendar_booked: false,
      }
    : null;

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-slate-800 font-semibold text-sm">כל הלידים</h2>
            <div className="relative">
              <Search className="absolute end-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
              <input
                type="text"
                value={query}
                onChange={(e) => { setQuery(e.target.value); setPage(0); }}
                placeholder="חיפוש שם או טלפון..."
                className="pe-9 ps-3 py-1.5 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 w-52"
              />
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100">
                  {COLUMNS.map((col) => (
                    <th
                      key={col}
                      className="text-start text-xs font-medium text-slate-400 uppercase tracking-wider px-6 py-3 whitespace-nowrap"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {paged.length === 0 ? (
                  <tr>
                    <td colSpan={COLUMNS.length} className="px-6 py-10 text-center text-slate-400 text-sm">
                      לא נמצאו לידים
                    </td>
                  </tr>
                ) : (
                  paged.map((lead) => (
                    <tr
                      key={lead.id}
                      onClick={() => setSelectedLead(lead)}
                      className="hover:bg-slate-50 transition-colors cursor-pointer group"
                    >
                      {/* Name */}
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-brand-100 flex items-center justify-center text-brand-700 font-semibold text-xs flex-shrink-0">
                            {(lead.name ?? "?").charAt(0).toUpperCase()}
                          </div>
                          <span className="font-medium text-slate-900 group-hover:text-brand-600 transition-colors">
                            {lead.name ?? <span className="text-slate-400">—</span>}
                          </span>
                        </div>
                      </td>
                      {/* Phone */}
                      <td className="px-6 py-4 text-slate-500 font-mono text-xs">
                        {lead.phone}
                      </td>
                      {/* Source */}
                      <td className="px-6 py-4">
                        {lead.source === "voice" ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                            <Phone className="w-3 h-3" />
                            Voice
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                            <MessageSquare className="w-3 h-3" />
                            WhatsApp
                          </span>
                        )}
                      </td>
                      {/* Service */}
                      <td className="px-6 py-4 text-slate-700">
                        {lead.service ?? <span className="text-slate-400">—</span>}
                      </td>
                      {/* Status */}
                      <td className="px-6 py-4">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLES[lead.status] ?? "bg-slate-100 text-slate-600"}`}>
                          {STATUS_LABELS[lead.status] ?? lead.status}
                        </span>
                      </td>
                      {/* Date */}
                      <td className="px-6 py-4 text-slate-400 text-xs whitespace-nowrap">
                        {formatDate(lead.created_at)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-6 py-3 border-t border-slate-100">
              <span className="text-xs text-slate-400">
                מציג {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} מתוך {filtered.length}
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="px-3 py-1 text-xs rounded-md border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
                >
                  הקודם
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page === totalPages - 1}
                  className="px-3 py-1 text-xs rounded-md border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
                >
                  הבא
                </button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {adaptedLead && (
        <LeadDetailPanel
          lead={adaptedLead}
          onClose={() => setSelectedLead(null)}
        />
      )}
    </>
  );
}
