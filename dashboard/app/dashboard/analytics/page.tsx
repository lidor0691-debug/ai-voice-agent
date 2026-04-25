export const dynamic = "force-dynamic";

import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase-server";
import { getUserContext } from "@/lib/user-context";
import { Header } from "@/components/layout/header";
import { ActivityChart } from "@/components/dashboard/activity-chart";
import { fetchLeads } from "@/lib/api";
import { MOCK_LEADS } from "@/lib/mock-data";
import { computeStats } from "@/lib/utils";
import { Card, CardHeader, CardContent } from "@/components/ui/card";

export default async function AnalyticsPage() {
  const client = await createSupabaseServerClient();
  const { data: { user } } = await client.auth.getUser();
  const ctx = getUserContext(user);
  if (!ctx?.isAdmin) redirect("/dashboard");
  let leads = MOCK_LEADS;
  try {
    leads = await fetchLeads();
  } catch {
    // backend unavailable — mock data is used as fallback
  }

  const stats = computeStats(leads);
  const testRidePct = stats.total ? Math.round((stats.testRides / stats.total) * 100) : 0;
  const appointmentPct = stats.total ? Math.round((stats.appointments / stats.total) * 100) : 0;
  const newLeadPct = stats.total ? Math.round((stats.newLeads / stats.total) * 100) : 0;

  // Intent breakdown — a lead with multiple intents counts once per intent
  const intentMap: Record<string, number> = {};
  leads.forEach((l) => {
    l.intents.forEach((v) => { intentMap[v] = (intentMap[v] ?? 0) + 1; });
  });
  const intentData = Object.entries(intentMap)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 6);
  const maxIntent = Math.max(...intentData.map(([, v]) => v), 1);

  // Top Honda models
  const modelMap: Record<string, number> = {};
  leads.forEach((l) => { if (l.model) modelMap[l.model] = (modelMap[l.model] ?? 0) + 1; });
  const topModels = Object.entries(modelMap).sort(([, a], [, b]) => b - a).slice(0, 5);
  const maxModel = Math.max(...topModels.map(([, v]) => v), 1);

  return (
    <>
      <Header title="אנליטיקה" subtitle="נתוני ביצועים ומגמות — Honda" />
      <main className="flex-1 overflow-y-auto p-8 space-y-6" dir="rtl">
        {/* Funnel */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[
            { label: "סך שיחות נכנסות", value: stats.total, bg: "bg-brand-50", text: "text-brand-700", bar: "bg-brand-500", pct: 100 },
            { label: "נסיעות מבחן", value: stats.testRides, bg: "bg-green-50", text: "text-green-700", bar: "bg-green-500", pct: testRidePct },
            { label: "תורים שנקבעו", value: stats.appointments, bg: "bg-blue-50", text: "text-blue-700", bar: "bg-blue-500", pct: appointmentPct },
          ].map(({ label, value, bg, text, bar, pct }) => (
            <Card key={label} className={`p-6 ${bg} border-0`}>
              <p className={`text-sm font-medium ${text}`}>{label}</p>
              <p className={`text-4xl font-bold ${text} mt-1 tabular-nums`}>{value}</p>
              <div className="mt-3 bg-white/60 rounded-full h-2">
                <div className={`${bar} h-2 rounded-full`} style={{ width: `${pct}%` }} />
              </div>
              <p className={`text-xs ${text} mt-1`}>{pct}% מסך הפניות</p>
            </Card>
          ))}
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-1">
            <ActivityChart leads={leads} />
          </div>

          {/* Intent breakdown */}
          <Card className="xl:col-span-1">
            <CardHeader>
              <h2 className="text-slate-800 font-semibold text-sm">פניות לפי כוונה</h2>
            </CardHeader>
            <CardContent className="space-y-3">
              {intentData.map(([label, count]) => (
                <div key={label}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-slate-700 font-medium">{label}</span>
                    <span className="text-slate-400 tabular-nums">{count}</span>
                  </div>
                  <div className="bg-slate-100 rounded-full h-2">
                    <div className="bg-brand-500 h-2 rounded-full" style={{ width: `${(count / maxIntent) * 100}%` }} />
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Top Honda models */}
          <Card className="xl:col-span-1">
            <CardHeader>
              <h2 className="text-slate-800 font-semibold text-sm">דגמים מבוקשים</h2>
            </CardHeader>
            <CardContent className="space-y-3">
              {topModels.map(([name, count]) => (
                <div key={name}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-slate-700 font-medium text-xs">{name}</span>
                    <span className="text-slate-400 tabular-nums">{count}</span>
                  </div>
                  <div className="bg-slate-100 rounded-full h-2">
                    <div className="bg-brand-500 h-2 rounded-full" style={{ width: `${(count / maxModel) * 100}%` }} />
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </main>
    </>
  );
}
