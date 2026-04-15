"use client";

import Link from "next/link";
import { Bot, Phone, BookOpen, Circle, ArrowRight } from "lucide-react";
import { Header } from "@/components/layout/header";
import { TestAgent } from "@/components/dashboard/test-agent";
import { useLanguage } from "@/context/language-context";
import type { AgentConfig, CallLog } from "@/types/database";

interface Props {
  agents: Pick<AgentConfig, "id" | "agent_name" | "is_active" | "system_prompt" | "first_message" | "phone_number">[] | null;
  calls: Pick<CallLog, "id" | "status" | "created_at">[] | null;
  knowledgeCount: number;
}

export function DashboardClientPage({ agents, calls, knowledgeCount }: Props) {
  const { t } = useLanguage();

  const totalAgents  = agents?.length ?? 0;
  const activeAgents = agents?.filter((a) => a.is_active).length ?? 0;
  const totalCalls   = calls?.length ?? 0;
  const recentCalls  = calls?.slice(0, 5) ?? [];

  const kpiCards = [
    { label: t.kpi_total_agents,    value: totalAgents,    icon: Bot,      color: "text-brand-400",   bg: "bg-brand-600/10",   href: "/dashboard/agents" },
    { label: t.kpi_active_agents,   value: activeAgents,   icon: Circle,   color: "text-emerald-400", bg: "bg-emerald-500/10", href: "/dashboard/agents" },
    { label: t.kpi_recent_calls,    value: totalCalls,     icon: Phone,    color: "text-blue-400",    bg: "bg-blue-500/10",    href: "/dashboard/calls" },
    { label: t.kpi_knowledge_items, value: knowledgeCount, icon: BookOpen, color: "text-amber-400",   bg: "bg-amber-500/10",   href: "/dashboard/knowledge" },
  ];

  return (
    <div className="flex-1 overflow-y-auto">
      <Header title={t.page_dashboard_title} subtitle={t.page_dashboard_subtitle} />

      <div className="p-8 space-y-6">
        {/* KPI cards */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          {kpiCards.map(({ label, value, icon: Icon, color, bg, href }) => (
            <Link
              key={label}
              href={href}
              className="group bg-surface-2 border border-border rounded-xl p-5 hover:border-brand-600/30 transition-all"
            >
              <div className={`w-9 h-9 rounded-xl ${bg} flex items-center justify-center mb-4`}>
                <Icon className={`w-4 h-4 ${color}`} />
              </div>
              <p className="text-2xl font-bold text-white">{value}</p>
              <p className="text-gray-500 text-xs mt-1">{label}</p>
            </Link>
          ))}
        </div>

        {/* Main grid */}
        <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
          {/* Test Agent */}
          <div className="xl:col-span-3">
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

          {/* Side panels */}
          <div className="xl:col-span-2 space-y-4">
            {/* Agents quick list */}
            <div className="bg-surface-2 border border-border rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-white text-sm font-medium">{t.your_agents}</h2>
                <Link href="/dashboard/agents" className="text-gray-500 hover:text-brand-400 text-xs flex items-center gap-1 transition-colors">
                  {t.view_all} <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
              {!agents?.length ? (
                <p className="text-gray-600 text-xs text-center py-4">{t.no_agents_yet}</p>
              ) : (
                <div className="space-y-1">
                  {agents.slice(0, 4).map((agent) => (
                    <Link
                      key={agent.id}
                      href={`/dashboard/agents/${agent.id}`}
                      className="flex items-center justify-between py-2 px-2 rounded-lg hover:bg-surface-3 transition-colors group"
                    >
                      <div className="flex items-center gap-2.5">
                        <div className="w-6 h-6 rounded-lg bg-brand-600/15 flex items-center justify-center">
                          <span className="text-brand-400 text-[10px] font-bold">
                            {agent.agent_name.charAt(0).toUpperCase()}
                          </span>
                        </div>
                        <span className="text-gray-300 text-sm group-hover:text-white transition-colors">
                          {agent.agent_name}
                        </span>
                      </div>
                      <span className={`w-1.5 h-1.5 rounded-full ${agent.is_active ? "bg-emerald-400" : "bg-gray-600"}`} />
                    </Link>
                  ))}
                </div>
              )}
            </div>

            {/* Recent calls */}
            <div className="bg-surface-2 border border-border rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-white text-sm font-medium">{t.kpi_recent_calls}</h2>
                <Link href="/dashboard/calls" className="text-gray-500 hover:text-brand-400 text-xs flex items-center gap-1 transition-colors">
                  {t.view_all} <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
              {recentCalls.length === 0 ? (
                <p className="text-gray-600 text-xs text-center py-4">{t.no_calls_yet}</p>
              ) : (
                <div className="space-y-1">
                  {recentCalls.map((call) => (
                    <div key={call.id} className="flex items-center justify-between py-1.5 px-2 rounded-lg">
                      <div className="flex items-center gap-2">
                        <Phone className="w-3 h-3 text-gray-600" />
                        <span className="text-gray-400 text-xs">
                          {new Date(call.created_at).toLocaleString("he-IL", {
                            month: "short", day: "numeric",
                            hour: "2-digit", minute: "2-digit",
                          })}
                        </span>
                      </div>
                      <span className={`text-xs font-medium ${
                        call.status === "completed" ? "text-emerald-400" :
                        call.status === "missed"    ? "text-amber-400"   :
                        "text-red-400"
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
      </div>
    </div>
  );
}
