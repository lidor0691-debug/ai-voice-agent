"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Users, ArrowRight, Loader2 } from "lucide-react";
import type { SupabaseLead } from "@/types/lead";

const AVATAR_GRADIENTS = [
  "linear-gradient(135deg, #8b5cf6, #6366f1)",
  "linear-gradient(135deg, #3b82f6, #06b6d4)",
  "linear-gradient(135deg, #10b981, #14b8a6)",
  "linear-gradient(135deg, #f59e0b, #ef4444)",
  "linear-gradient(135deg, #ec4899, #a855f7)",
];

function maskPhone(phone: string): string {
  if (phone.length < 8) return phone;
  return phone.slice(0, 4) + "••••" + phone.slice(-3);
}

function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "עכשיו";
  if (mins < 60) return `לפני ${mins} דק׳`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `לפני ${hours} שע׳`;
  const days = Math.floor(hours / 24);
  return `לפני ${days} ימים`;
}

export function MobileLeadList() {
  const [leads, setLeads] = useState<SupabaseLead[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/leads");
        if (!res.ok) return;
        const data = await res.json();
        setLeads((data.leads ?? []).slice(0, 5));
      } catch { /* silent */ }
      finally { setLoading(false); }
    })();
  }, []);

  return (
    <div className="space-y-3" dir="rtl">
      {/* Section header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="w-4 h-4 text-brand-400" />
          <p className="text-white text-sm font-semibold">לידים אחרונים</p>
        </div>
        <Link
          href="/dashboard/leads"
          className="text-brand-400 text-xs flex items-center gap-1 hover:text-brand-300 transition-colors"
        >
          הצג הכל <ArrowRight className="w-3 h-3" />
        </Link>
      </div>

      {/* Loading */}
      {loading && (
        <div className="card flex items-center justify-center py-6">
          <Loader2 className="w-5 h-5 text-gray-500 animate-spin" />
        </div>
      )}

      {/* Empty */}
      {!loading && leads.length === 0 && (
        <div className="card flex items-center justify-center py-6">
          <p className="text-gray-500 text-sm">אין לידים חדשים</p>
        </div>
      )}

      {/* Lead rows */}
      {!loading && leads.length > 0 && (
        <div className="card overflow-hidden divide-y divide-border">
          {leads.map((lead, i) => {
            const displayName = lead.name || maskPhone(lead.phone);
            const initial = (lead.name ?? lead.phone)[0]?.toUpperCase() ?? "?";
            const gradient = AVATAR_GRADIENTS[i % AVATAR_GRADIENTS.length];

            return (
              <Link
                key={lead.id}
                href="/dashboard/leads"
                className="flex items-center gap-3 px-4 py-3 min-h-[56px] hover:bg-surface-3 transition-colors"
              >
                {/* Avatar */}
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-xs font-bold flex-shrink-0"
                  style={{ background: gradient }}
                >
                  {initial}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm font-medium truncate">{displayName}</p>
                  <p className="text-gray-500 text-[11px]">{relativeTime(lead.created_at)}</p>
                </div>

                {/* Phone */}
                <span className="text-gray-600 text-xs flex-shrink-0">
                  {maskPhone(lead.phone)}
                </span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
