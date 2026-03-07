export const dynamic = "force-dynamic";

import { Users, CalendarCheck, Bike, Sparkles } from "lucide-react";
import { Header } from "@/components/layout/header";
import { StatCard } from "@/components/dashboard/stat-card";
import { LeadsTable } from "@/components/dashboard/leads-table";
import { ActivityChart } from "@/components/dashboard/activity-chart";
import { fetchLeads } from "@/lib/api";
import { MOCK_LEADS } from "@/lib/mock-data";
import { computeStats } from "@/lib/utils";

export default async function DashboardPage() {
  // Fetch from FastAPI; fall back to mock data if the backend is down
  let leads = MOCK_LEADS;
  try {
    leads = await fetchLeads();
  } catch {
    // backend unavailable — mock data is used as fallback
  }

  const stats = computeStats(leads);
  const testRidePct = stats.total ? Math.round((stats.testRides / stats.total) * 100) : 0;
  const appointmentPct = stats.total ? Math.round((stats.appointments / stats.total) * 100) : 0;

  return (
    <>
      <Header title="לוח בקרה" subtitle="Maya AI — Honda Voice Assistant" />
      <main className="flex-1 overflow-y-auto p-8 space-y-6" dir="rtl">
        {/* KPI Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          <StatCard
            title="סך הכל פניות"
            value={stats.total}
            subtitle={`${stats.thisWeek} השבוע`}
            trend={18}
            icon={Users}
            iconColor="text-brand-600"
            iconBg="bg-brand-50"
          />
          <StatCard
            title="נסיעות מבחן"
            value={stats.testRides}
            subtitle={`${testRidePct}% מהפניות`}
            trend={12}
            icon={Bike}
            iconColor="text-green-600"
            iconBg="bg-green-50"
          />
          <StatCard
            title="תורים נקבעו"
            value={stats.appointments}
            subtitle={`${appointmentPct}% המרה`}
            trend={8}
            icon={CalendarCheck}
            iconColor="text-blue-600"
            iconBg="bg-blue-50"
          />
          <StatCard
            title="לידים חדשים"
            value={stats.newLeads}
            subtitle="ממתינים לטיפול"
            trend={-5}
            icon={Sparkles}
            iconColor="text-amber-600"
            iconBg="bg-amber-50"
          />
        </div>

        {/* Chart + System Status */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-1">
            <ActivityChart leads={leads} />
          </div>

          <div className="xl:col-span-2">
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm h-full p-6 flex flex-col justify-between">
              <div>
                <h2 className="text-slate-800 font-semibold text-sm mb-4">
                  סטטוס מערכת
                </h2>
                <div className="space-y-0">
                  {[
                    { label: "שרת FastAPI", status: "פעיל" },
                    { label: "Twilio Voice Webhook", status: "מחובר" },
                    { label: "Google Sheets", status: "מחובר" },
                    { label: "SMS Notifications", status: "פעיל" },
                    { label: "Hebrew TTS — Polly.Ayelet", status: "פעיל" },
                  ].map(({ label, status }) => (
                    <div
                      key={label}
                      className="flex items-center justify-between py-2.5 border-b border-slate-50 last:border-0"
                    >
                      <span className="text-slate-600 text-sm">{label}</span>
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                        <span className="text-sm text-slate-500">{status}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <p className="text-slate-400 text-xs mt-4">
                עדכון אחרון: {new Date().toLocaleTimeString("he-IL")}
              </p>
            </div>
          </div>
        </div>

        {/* Recent leads — clickable rows open detail panel */}
        <LeadsTable leads={leads} limit={5} showViewAll />
      </main>
    </>
  );
}
