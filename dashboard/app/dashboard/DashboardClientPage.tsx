"use client";

import Link from "next/link";
import { Bot, Phone, BookOpen, Users, ArrowRight } from "lucide-react";
import { Header } from "@/components/layout/header";
import { TestAgent } from "@/components/dashboard/test-agent";
import { useLanguage } from "@/context/language-context";
import type { AgentConfig, CallLog } from "@/types/database";

interface Props {
  agents: Pick<AgentConfig, "id" | "agent_name" | "is_active" | "system_prompt" | "first_message" | "phone_number">[] | null;
  calls:  Pick<CallLog, "id" | "status" | "created_at">[] | null;
  knowledgeCount: number;
}

// Simple 20-bar sparkline — heights as % of max
const CHART_BARS = [8,12,22,45,70,95,88,60,75,50,68,85,72,55,40,30,20,14,9,6];

export function DashboardClientPage({ agents, calls, knowledgeCount }: Props) {
  const { t } = useLanguage();

  const totalAgents  = agents?.length ?? 0;
  const activeAgents = agents?.filter((a) => a.is_active).length ?? 0;
  const totalCalls   = calls?.length ?? 0;
  const recentCalls  = calls?.slice(0, 5) ?? [];

  const kpiCards = [
    {
      label: t.kpi_total_agents, value: totalAgents,
      icon: Bot, colorText: "text-brand-400", colorBg: "bg-brand-500/10",
      glowClass: "kpi-glow-violet", href: "/dashboard/agents",
    },
    {
      label: t.kpi_active_agents, value: activeAgents,
      icon: Users, colorText: "text-emerald-400", colorBg: "bg-emerald-500/10",
      glowClass: "kpi-glow-green", href: "/dashboard/agents",
    },
    {
      label: t.kpi_recent_calls, value: totalCalls,
      icon: Phone, colorText: "text-blue-400", colorBg: "bg-blue-500/10",
      glowClass: "kpi-glow-blue", href: "/dashboard/calls",
    },
    {
      label: t.kpi_knowledge_items, value: knowledgeCount,
      icon: BookOpen, colorText: "text-amber-400", colorBg: "bg-amber-500/10",
      glowClass: "kpi-glow-amber", href: "/dashboard/knowledge",
    },
  ];

  const maxBar = Math.max(...CHART_BARS);

  return (
    <div className="flex-1 overflow-y-auto">
      <Header title={t.page_dashboard_title} subtitle={t.page_dashboard_subtitle} />

      <div className="p-6 space-y-5 bg-surface-0 min-h-full">

        {/* KPI Row */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          {kpiCards.map(({ label, value, icon: Icon, colorText, colorBg, glowClass, href }) => (
            <Link
              key={label}
              href={href}
              className={`relative card p-5 hover:border-brand-500/30 transition-all overflow-hidden ${glowClass}`}
            >
              <div className={`w-9 h-9 rounded-xl ${colorBg} flex items-center justify-center mb-4`}>
                <Icon className={`w-4 h-4 ${colorText}`} />
              </div>
              <p className="text-2xl font-extrabold text-white tracking-tight">{value}</p>
              <p className="text-gray-600 text-[11px] mt-1">{label}</p>
            </Link>
          ))}
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 xl:grid-cols-5 gap-5">

          {/* Voice Activity Chart */}
          <div className="xl:col-span-3 card p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="text-white text-sm font-semibold">פעילות קולית</p>
                <p className="text-gray-600 text-[11px] mt-0.5">24 שעות אחרונות</p>
              </div>
            </div>
            {/* Bar chart */}
            <div className="flex items-end gap-1.5 h-24">
              {CHART_BARS.map((h, i) => {
                const pct = (h / maxBar) * 100;
                const isPeak = pct >= 80;
                const isHi   = pct >= 50 && !isPeak;
                return (
                  <div
                    key={i}
                    style={{ height: `${pct}%` }}
                    className={`flex-1 rounded-t-sm transition-all ${
                      isPeak
                        ? "bg-brand-500 shadow-glow-sm"
                        : isHi
                        ? "bg-brand-500/40"
                        : "bg-surface-3"
                    }`}
                  />
                );
              })}
            </div>
            <div className="flex justify-between mt-2">
              {["00:00","04:00","08:00","12:00","16:00","20:00","23:59"].map((l) => (
                <span key={l} className="text-[9px] text-gray-700">{l}</span>
              ))}
            </div>
          </div>

          {/* Right column */}
          <div className="xl:col-span-2 space-y-4">

            {/* Agents quick list */}
            <div className="card p-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-white text-[13px] font-semibold">{t.your_agents}</h2>
                <Link href="/dashboard/agents" className="text-gray-600 hover:text-brand-400 text-[11px] flex items-center gap-1 transition-colors">
                  {t.view_all} <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
              {!agents?.length ? (
                <p className="text-gray-700 text-[11px] text-center py-4">{t.no_agents_yet}</p>
              ) : (
                <div className="space-y-1">
                  {agents.slice(0, 4).map((agent) => (
                    <Link
                      key={agent.id}
                      href={`/dashboard/agents/${agent.id}`}
                      className="flex items-center justify-between py-2 px-2 rounded-xl hover:bg-surface-3 transition-colors group"
                    >
                      <div className="flex items-center gap-2.5">
                        <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-brand-500/20 to-indigo-500/20 border border-brand-500/20 flex items-center justify-center">
                          <span className="text-brand-400 text-[10px] font-bold">
                            {agent.agent_name.charAt(0).toUpperCase()}
                          </span>
                        </div>
                        <span className="text-gray-400 text-[13px] group-hover:text-white transition-colors">
                          {agent.agent_name}
                        </span>
                      </div>
                      <span
                        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                        style={agent.is_active ? { background: "#10b981", boxShadow: "0 0 6px #10b981" } : { background: "#334155" }}
                      />
                    </Link>
                  ))}
                </div>
              )}
            </div>

            {/* Recent Calls */}
            <div className="card p-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-white text-[13px] font-semibold">{t.kpi_recent_calls}</h2>
                <Link href="/dashboard/calls" className="text-gray-600 hover:text-brand-400 text-[11px] flex items-center gap-1 transition-colors">
                  {t.view_all} <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
              {recentCalls.length === 0 ? (
                <p className="text-gray-700 text-[11px] text-center py-4">{t.no_calls_yet}</p>
              ) : (
                <div className="space-y-1">
                  {recentCalls.map((call) => (
                    <div
                      key={call.id}
                      className="flex items-center justify-between py-1.5 px-2 rounded-xl border-e-2 border-transparent"
                      style={{
                        borderColor:
                          call.status === "completed" ? "#10b981"
                          : call.status === "missed"   ? "#f59e0b"
                          : "#ef4444",
                      }}
                    >
                      <span className="text-gray-500 text-[11px]">
                        {new Date(call.created_at).toLocaleString("he-IL", {
                          month: "short", day: "numeric",
                          hour: "2-digit", minute: "2-digit",
                        })}
                      </span>
                      <span className={`text-[11px] font-semibold ${
                        call.status === "completed" ? "text-emerald-400"
                        : call.status === "missed"   ? "text-amber-400"
                        : "text-red-400"
                      }`}>
                        {call.status ?? "—"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Test Agent */}
        <TestAgent
          agents={
            agents?.map((a) => ({
              id: a.id,
              agent_name: a.agent_name,
              system_prompt: a.system_prompt,
              first_message: a.first_message,
            })) ?? []
          }
        />
      </div>
    </div>
  );
}
