"use client";

import Link from "next/link";
import { Bot, Phone, Users, Clock, ArrowRight, Plus } from "lucide-react";
import { Header } from "@/components/layout/header";
import { TestAgent } from "@/components/dashboard/test-agent";
import { useLanguage } from "@/context/language-context";
import type { AgentConfig, CallLog } from "@/types/database";

interface Props {
  agents: Pick<AgentConfig, "id" | "agent_name" | "is_active" | "system_prompt" | "first_message" | "phone_number">[] | null;
  calls:  Pick<CallLog, "id" | "status" | "created_at">[] | null;
  knowledgeCount: number;
}

// 20 bars — mountain shape peaking around bar 6-7 and secondary peak at 12
const CHART_BARS = [
  { h: 15, cls: "" },
  { h: 8,  cls: "" },
  { h: 12, cls: "" },
  { h: 35, cls: "hi" },
  { h: 55, cls: "hi" },
  { h: 88, cls: "peak" },
  { h: 95, cls: "peak" },
  { h: 72, cls: "hi" },
  { h: 60, cls: "hi" },
  { h: 45, cls: "" },
  { h: 68, cls: "hi" },
  { h: 82, cls: "peak" },
  { h: 70, cls: "hi" },
  { h: 50, cls: "" },
  { h: 38, cls: "" },
  { h: 28, cls: "" },
  { h: 22, cls: "" },
  { h: 18, cls: "" },
  { h: 10, cls: "" },
  { h: 6,  cls: "" },
];

const AGENT_GRADIENTS = [
  { c1: "#8b5cf6", c2: "#6366f1" },
  { c1: "#3b82f6", c2: "#06b6d4" },
  { c1: "#10b981", c2: "#14b8a6" },
  { c1: "#f59e0b", c2: "#ef4444" },
  { c1: "#ec4899", c2: "#a855f7" },
];


export function DashboardClientPage({ agents, calls, knowledgeCount }: Props) {
  const { t } = useLanguage();

  const totalAgents  = agents?.length ?? 0;
  const activeAgents = agents?.filter((a) => a.is_active).length ?? 0;
  const totalCalls   = calls?.length ?? 0;
  const recentCalls  = calls?.slice(0, 5) ?? [];

  const kpiCards = [
    { label: t.kpi_active_agents, value: activeAgents, icon: Users,  color: "#a78bfa", bg: "rgba(139,92,246,0.15)", glow: "rgba(139,92,246,0.12)", delta: `+${activeAgents}`, up: true },
    { label: t.kpi_recent_calls,  value: totalCalls,   icon: Phone,  color: "#10b981", bg: "rgba(16,185,129,0.12)",  glow: "rgba(16,185,129,0.08)",  delta: "↑ 24%", up: true },
    { label: t.kpi_total_agents,  value: totalAgents,  icon: Bot,    color: "#60a5fa", bg: "rgba(59,130,246,0.12)",  glow: "rgba(59,130,246,0.08)",  delta: `↑ ${totalAgents}`, up: true },
    { label: t.kpi_knowledge_items, value: knowledgeCount, icon: Clock, color: "#fbbf24", bg: "rgba(245,158,11,0.12)", glow: "rgba(245,158,11,0.08)", delta: "—", up: false },
  ];

  return (
    <div className="flex-1 overflow-y-auto">
      <Header title={t.page_dashboard_title} subtitle={t.page_dashboard_subtitle} />

      <div className="p-5 space-y-4 bg-surface-0 min-h-full">

        {/* KPI Row */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
          {kpiCards.map(({ label, value, icon: Icon, color, bg, glow, delta, up }) => (
            <div
              key={label}
              className="relative card p-4 flex items-center gap-3 overflow-hidden"
              style={{ ["--kpi-glow" as string]: glow }}
            >
              {/* radial glow */}
              <div
                className="absolute inset-0 pointer-events-none rounded-[14px]"
                style={{ background: `radial-gradient(ellipse at top right, ${glow} 0%, transparent 60%)` }}
              />
              <div
                className="w-9 h-9 rounded-[10px] flex items-center justify-center flex-shrink-0"
                style={{ background: bg, color }}
              >
                <Icon className="w-4 h-4" style={{ stroke: color }} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-2xl font-extrabold text-white tracking-tight leading-none">{value}</p>
                <p className="text-gray-600 text-[10px] mt-1">{label}</p>
              </div>
              <span
                className="text-[9px] font-semibold px-1.5 py-0.5 rounded flex-shrink-0"
                style={up
                  ? { color: "#10b981", background: "rgba(16,185,129,0.1)" }
                  : { color: "#f59e0b", background: "rgba(245,158,11,0.1)" }
                }
              >
                {delta}
              </span>
            </div>
          ))}
        </div>

        {/* Main 3-column grid */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4" style={{ minHeight: 0 }}>

          {/* Col 1: Voice Activity Chart */}
          <div className="card p-4 flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-white text-[13px] font-semibold">פעילות קולית — 24 שעות</p>
                <p className="text-gray-600 text-[10px] mt-0.5">שיחות לפי שעה</p>
              </div>
              <Link href="/dashboard/calls" className="text-brand-400 text-[10px] flex items-center gap-1 hover:text-brand-300 transition-colors">
                הצג הכל <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            {/* Bars */}
            <div className="flex items-end gap-[3px] flex-1" style={{ minHeight: 120 }}>
              {CHART_BARS.map(({ h, cls }, i) => (
                <div
                  key={i}
                  className="flex-1"
                  style={{ height: `${h}%`, borderRadius: "3px 3px 0 0", ...
                    cls === "peak"
                      ? { background: "linear-gradient(180deg,#a78bfa,rgba(139,92,246,0.6))", boxShadow: "0 -4px 12px rgba(139,92,246,0.3)" }
                      : cls === "hi"
                      ? { background: "linear-gradient(180deg,#8b5cf6,rgba(139,92,246,0.4))" }
                      : { background: "rgba(139,92,246,0.2)" }
                  }}
                />
              ))}
            </div>
            <div className="flex justify-between mt-2">
              {["00:00","06:00","09:00","12:00","15:00","18:00","21:00"].map((l) => (
                <span key={l} className="text-[8px] text-gray-700">{l}</span>
              ))}
            </div>
          </div>

          {/* Col 2: Agents List */}
          <div className="card p-4 flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-white text-[13px] font-semibold">{t.your_agents}</p>
                <p className="text-gray-600 text-[10px] mt-0.5">
                  {activeAgents} מתוך {totalAgents} פעילים
                </p>
              </div>
              <Link href="/dashboard/agents" className="text-brand-400 text-[10px] flex items-center gap-1 hover:text-brand-300 transition-colors">
                נהל <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            <div className="flex flex-col gap-1.5 flex-1">
              {!agents?.length ? (
                <div className="flex-1 flex flex-col items-center justify-center text-center py-8">
                  <p className="text-gray-600 text-[11px]">{t.no_agents_yet}</p>
                  <Link href="/dashboard/agents/new" className="mt-3 btn-primary flex items-center gap-1.5 text-[11px] px-3 py-1.5">
                    <Plus className="w-3 h-3" /> {t.new_agent_btn}
                  </Link>
                </div>
              ) : (
                agents.slice(0, 5).map((agent, i) => {
                  const grad = AGENT_GRADIENTS[i % AGENT_GRADIENTS.length];
                  return (
                    <Link
                      key={agent.id}
                      href={`/dashboard/agents/${agent.id}`}
                      className="flex items-center gap-2.5 px-2.5 py-2 rounded-[10px] border border-border hover:bg-surface-3 transition-all group"
                      style={{ background: "rgba(255,255,255,0.02)" }}
                    >
                      <div
                        className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-[11px] font-bold flex-shrink-0"
                        style={{ background: `linear-gradient(135deg,${grad.c1},${grad.c2})` }}
                      >
                        {agent.agent_name.charAt(0).toUpperCase()}
                      </div>
                      <span className="text-gray-300 text-[12px] font-medium flex-1 group-hover:text-white transition-colors truncate">
                        {agent.agent_name}
                      </span>
                      <span className="text-gray-600 text-[10px]">
                        {agent.phone_number ?? "—"}
                      </span>
                      <span
                        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                        style={agent.is_active
                          ? { background: "#10b981", boxShadow: "0 0 6px #10b981" }
                          : { background: "#334155" }
                        }
                      />
                    </Link>
                  );
                })
              )}
            </div>
          </div>

          {/* Col 3: Chat + Recent Calls */}
          <div className="flex flex-col gap-4">

            {/* Test Agent chat */}
            <div className="card overflow-hidden flex-1">
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

            {/* Recent Calls feed */}
            <div className="card p-4">
              <div className="flex items-center justify-between mb-3">
                <p className="text-white text-[13px] font-semibold">{t.kpi_recent_calls}</p>
                <Link href="/dashboard/calls" className="text-brand-400 text-[10px] flex items-center gap-1 hover:text-brand-300 transition-colors">
                  {t.view_all} <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
              {recentCalls.length === 0 ? (
                <p className="text-gray-700 text-[11px] text-center py-3">{t.no_calls_yet}</p>
              ) : (
                <div className="flex flex-col gap-1">
                  {recentCalls.map((call) => (
                    <div
                      key={call.id}
                      className="flex items-center gap-2 px-2.5 py-2 rounded-lg"
                      style={{
                        background: "rgba(255,255,255,0.02)",
                        borderRight: `2px solid ${
                          call.status === "completed" ? "#10b981"
                          : call.status === "missed"  ? "#f59e0b"
                          : "#ef4444"
                        }`,
                      }}
                    >
                      <span className="text-gray-600 text-[9px] w-8 flex-shrink-0">
                        {new Date(call.created_at).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" })}
                      </span>
                      <span className="flex-1 text-gray-500 text-[10px] truncate">
                        {new Date(call.created_at).toLocaleDateString("he-IL", { month: "short", day: "numeric" })}
                      </span>
                      <span className="text-gray-600 text-[9px]">—</span>
                      <span
                        className="text-[8.5px] font-semibold px-1.5 py-0.5 rounded flex-shrink-0"
                        style={
                          call.status === "completed"
                            ? { color: "#10b981", background: "rgba(16,185,129,0.1)" }
                            : call.status === "missed"
                            ? { color: "#f59e0b", background: "rgba(245,158,11,0.1)" }
                            : { color: "#ef4444", background: "rgba(239,68,68,0.1)" }
                        }
                      >
                        {call.status === "completed" ? t.status_completed
                          : call.status === "missed" ? t.status_missed
                          : t.status_failed}
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
