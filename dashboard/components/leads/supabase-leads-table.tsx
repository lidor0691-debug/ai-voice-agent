"use client";

import { useEffect, useState } from "react";
import { Search, Phone, MessageSquare } from "lucide-react";
import { LeadDetailPanel } from "@/components/dashboard/lead-detail-panel";
import { formatDate, displayPhone, displayLeadName } from "@/lib/utils";
import type { SupabaseLead } from "@/types/lead";

const STATUS_CONFIG: Record<string, { label: string; text: string; bg: string; border: string }> = {
  new:       { label: "חדש",      text: "text-amber-400",   bg: "bg-amber-500/10",   border: "border-amber-500/20" },
  contacted: { label: "בטיפול",   text: "text-blue-400",    bg: "bg-blue-500/10",    border: "border-blue-500/20" },
  scheduled: { label: "תור נקבע", text: "text-brand-400",   bg: "bg-brand-500/10",   border: "border-brand-500/20" },
  closed:    { label: "סגור",     text: "text-gray-500",    bg: "bg-surface-3",      border: "border-border" },
};

const COLUMNS = ["שם", "טלפון", "מקור", "שירות", "סטטוס", "תאריך"];
const PAGE_SIZE = 50;

interface Props {
  leads: SupabaseLead[];
}

export function SupabaseLeadsTable({ leads: leadsProp }: Props) {
  const [leads, setLeads] = useState<SupabaseLead[]>(leadsProp);
  const [query, setQuery] = useState("");
  const [selectedLead, setSelectedLead] = useState<SupabaseLead | null>(null);
  const [page, setPage] = useState(0);

  // Keep local state in sync if parent re-fetches.
  useEffect(() => { setLeads(leadsProp); }, [leadsProp]);

  // Expose the currently open lead to the dashboard assistant (Maya FAB).
  // The FAB lives outside this component tree (DashboardShell), so we use
  // sessionStorage as a tiny cross-component handoff.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (selectedLead) {
      sessionStorage.setItem("maya:active_lead_id", selectedLead.id);
    } else {
      sessionStorage.removeItem("maya:active_lead_id");
    }
    return () => {
      if (typeof window !== "undefined") {
        sessionStorage.removeItem("maya:active_lead_id");
      }
    };
  }, [selectedLead]);

  const handleLeadUpdated = (id: string, patch: { name?: string | null }) => {
    setLeads((prev) => prev.map((l) => (l.id === id ? { ...l, ...patch } : l)));
    setSelectedLead((prev) => (prev && prev.id === id ? { ...prev, ...patch } : prev));
  };

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

  const adaptedLead = selectedLead
    ? {
        id: selectedLead.id,
        name: selectedLead.name ?? "",
        phone: selectedLead.phone,
        model: selectedLead.service ?? "",
        intents: [],
        mileage: "",
        appointment_time: selectedLead.appointment_at ?? null,
        created_at: selectedLead.created_at,
        status: selectedLead.status,
        source: selectedLead.source,
        sms_sent: false,
        calendar_booked: Boolean(selectedLead.appointment_at),
        notes: selectedLead.notes ?? null,
        last_call_topic: selectedLead.last_call_topic ?? null,
        last_call_summary: selectedLead.last_call_summary ?? null,
      }
    : null;

  return (
    <>
      <div className="card overflow-hidden">
        {/* Table header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-white font-semibold text-[13px]">כל הלידים</h2>
          <div className="relative">
            <Search className="absolute end-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-600" />
            <input
              type="text"
              value={query}
              onChange={(e) => { setQuery(e.target.value); setPage(0); }}
              placeholder="חיפוש שם או טלפון..."
              className="pe-9 ps-3 py-1.5 text-xs bg-surface-2 border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500 text-white placeholder-gray-600 w-52 transition-colors"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                {COLUMNS.map((col) => (
                  <th
                    key={col}
                    className="text-start text-[11px] font-medium text-gray-600 px-5 py-3 whitespace-nowrap"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {paged.length === 0 ? (
                <tr>
                  <td colSpan={COLUMNS.length} className="px-6 py-10 text-center text-gray-600 text-sm">
                    לא נמצאו לידים
                  </td>
                </tr>
              ) : (
                paged.map((lead) => {
                  const cfg = STATUS_CONFIG[lead.status];
                  return (
                    <tr
                      key={lead.id}
                      onClick={() => setSelectedLead(lead)}
                      className="border-b border-border last:border-0 hover:bg-surface-2 transition-colors cursor-pointer group"
                    >
                      {/* Name */}
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-2.5">
                          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500/20 to-indigo-500/20 border border-brand-500/20 flex items-center justify-center text-brand-400 font-bold text-[11px] flex-shrink-0">
                            {(lead.name ?? "?").charAt(0).toUpperCase()}
                          </div>
                          <span className="font-medium text-gray-300 group-hover:text-white transition-colors text-[13px]">
                            {lead.name ? displayLeadName(lead.name) : <span className="text-gray-600">ללא שם</span>}
                          </span>
                        </div>
                      </td>
                      {/* Phone */}
                      <td className="px-5 py-3.5 text-gray-500 font-mono text-[12px]">
                        {displayPhone(lead.phone)}
                      </td>
                      {/* Source */}
                      <td className="px-5 py-3.5">
                        {lead.source === "voice" ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20">
                            <Phone className="w-3 h-3" />
                            Voice
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            <MessageSquare className="w-3 h-3" />
                            WhatsApp
                          </span>
                        )}
                      </td>
                      {/* Service */}
                      <td className="px-5 py-3.5 text-gray-400 text-[13px]">
                        {lead.service ?? <span className="text-gray-700">—</span>}
                      </td>
                      {/* Status */}
                      <td className="px-5 py-3.5">
                        {cfg ? (
                          <span className={`px-2.5 py-1 rounded-full text-[11px] font-semibold border ${cfg.text} ${cfg.bg} ${cfg.border}`}>
                            {cfg.label}
                          </span>
                        ) : (
                          <span className="text-gray-600 text-[11px]">{lead.status}</span>
                        )}
                      </td>
                      {/* Date */}
                      <td className="px-5 py-3.5 text-gray-600 text-[12px] whitespace-nowrap">
                        {formatDate(lead.created_at)}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-border">
            <span className="text-[11px] text-gray-600">
              מציג {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} מתוך {filtered.length}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-3 py-1 text-[11px] rounded-lg border border-border text-gray-400 disabled:opacity-40 hover:bg-surface-3 hover:text-white transition-colors"
              >
                הקודם
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page === totalPages - 1}
                className="px-3 py-1 text-[11px] rounded-lg border border-border text-gray-400 disabled:opacity-40 hover:bg-surface-3 hover:text-white transition-colors"
              >
                הבא
              </button>
            </div>
          </div>
        )}
      </div>

      {adaptedLead && (
        <LeadDetailPanel
          lead={adaptedLead}
          onClose={() => setSelectedLead(null)}
          onLeadUpdated={handleLeadUpdated}
        />
      )}
    </>
  );
}
