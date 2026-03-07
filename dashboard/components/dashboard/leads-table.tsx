"use client";

import { useState } from "react";
import { Search, ChevronLeft } from "lucide-react";
import Link from "next/link";
import { StatusBadge, BoolBadge, Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { formatDate, maskPhone } from "@/lib/utils";
import { LeadDetailPanel } from "@/components/dashboard/lead-detail-panel";
import type { Lead } from "@/types/lead";

interface LeadsTableProps {
  leads: Lead[];
  limit?: number;
  showSearch?: boolean;
  showViewAll?: boolean;
}

const COLUMNS = ["שם לקוח", "טלפון", "דגם", "כוונה", "סטטוס", "SMS", "יומן", "תאריך"];

export function LeadsTable({
  leads,
  limit,
  showSearch = false,
  showViewAll = false,
}: LeadsTableProps) {
  const [query, setQuery] = useState("");
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);

  const filtered = leads
    .filter((l) => {
      if (!query) return true;
      const q = query.toLowerCase();
      return (
        l.name.includes(q) ||
        l.model.toLowerCase().includes(q) ||
        l.phone.includes(q) ||
        l.intents.some((v) => v.includes(q))
      );
    })
    .slice(0, limit);

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-slate-800 font-semibold text-sm whitespace-nowrap">
              {showViewAll ? "פניות אחרונות" : "כל הפניות"}
            </h2>
            <div className="flex items-center gap-3">
              {showSearch && (
                <div className="relative">
                  <Search className="absolute end-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                  <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="חיפוש פנייה..."
                    className="pe-9 ps-3 py-1.5 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 w-52"
                  />
                </div>
              )}
              {showViewAll && (
                <Link
                  href="/dashboard/leads"
                  className="flex items-center gap-1 text-brand-600 hover:text-brand-700 text-sm font-medium transition-colors"
                >
                  הצג הכל
                  <ChevronLeft className="w-3.5 h-3.5" />
                </Link>
              )}
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
                {filtered.length === 0 ? (
                  <tr>
                    <td
                      colSpan={COLUMNS.length}
                      className="px-6 py-10 text-center text-slate-400 text-sm"
                    >
                      לא נמצאו פניות
                    </td>
                  </tr>
                ) : (
                  filtered.map((lead) => (
                    <tr
                      key={lead.id}
                      onClick={() => setSelectedLead(lead)}
                      className="hover:bg-slate-50 transition-colors cursor-pointer group"
                    >
                      {/* Name */}
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-brand-100 flex items-center justify-center text-brand-700 font-semibold text-xs flex-shrink-0">
                            {lead.name.charAt(0)}
                          </div>
                          <span className="font-medium text-slate-900 group-hover:text-brand-600 transition-colors">
                            {lead.name}
                          </span>
                        </div>
                      </td>
                      {/* Phone */}
                      <td className="px-6 py-4 text-slate-500 font-mono text-xs">
                        {maskPhone(lead.phone)}
                      </td>
                      {/* Model */}
                      <td className="px-6 py-4 text-slate-700 font-medium max-w-[180px] truncate">
                        {lead.model}
                      </td>
                      {/* Intents */}
                      <td className="px-6 py-4">
                        <div className="flex flex-wrap gap-1">
                          {lead.intents.length > 0
                            ? lead.intents.map((v) => (
                                <Badge key={v} variant="default" className="text-xs">{v}</Badge>
                              ))
                            : <span className="text-slate-400 text-xs">—</span>
                          }
                        </div>
                      </td>
                      {/* Status */}
                      <td className="px-6 py-4">
                        <StatusBadge status={lead.status} />
                      </td>
                      {/* SMS */}
                      <td className="px-6 py-4">
                        <BoolBadge value={lead.sms_sent} labelTrue="נשלח" />
                      </td>
                      {/* Calendar */}
                      <td className="px-6 py-4">
                        <BoolBadge value={lead.calendar_booked} labelTrue="נקבע" />
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
        </CardContent>
      </Card>

      <LeadDetailPanel
        lead={selectedLead}
        onClose={() => setSelectedLead(null)}
      />
    </>
  );
}
