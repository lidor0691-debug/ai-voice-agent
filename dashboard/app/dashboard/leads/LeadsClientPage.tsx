"use client";

import { Users, CalendarDays, Sparkles, Clock } from "lucide-react";
import { Header } from "@/components/layout/header";
import { StatCard } from "@/components/dashboard/stat-card";
import { SupabaseLeadsTable } from "@/components/leads/supabase-leads-table";
import type { LeadsApiResponse } from "@/types/lead";

interface Props {
  data: LeadsApiResponse;
}

export function LeadsClientPage({ data }: Props) {
  const { leads, stats } = data;

  return (
    <>
      <Header title="לידים" subtitle={`${stats.total} לידים בסך הכל`} />
      <main className="flex-1 overflow-y-auto p-8 space-y-6" dir="rtl">

        {/* Stats Row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            title="סה״כ לידים"
            value={stats.total}
            icon={Users}
            iconBg="bg-brand-50"
            iconColor="text-brand-600"
          />
          <StatCard
            title="היום"
            value={stats.today}
            icon={CalendarDays}
            iconBg="bg-green-50"
            iconColor="text-green-600"
          />
          <StatCard
            title="חדשים"
            value={stats.new}
            icon={Sparkles}
            iconBg="bg-yellow-50"
            iconColor="text-yellow-600"
          />
          <StatCard
            title="בטיפול"
            value={stats.contacted}
            icon={Clock}
            iconBg="bg-blue-50"
            iconColor="text-blue-600"
          />
        </div>

        {/* Source breakdown */}
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400 font-medium">מקור:</span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
            📞 Voice — {stats.voice}
          </span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
            💬 WhatsApp — {stats.whatsapp}
          </span>
        </div>

        {/* Table */}
        <SupabaseLeadsTable leads={leads} />
      </main>
    </>
  );
}
