"use client";

import { Phone, Clock, CheckCircle, XCircle, AlertCircle } from "lucide-react";
import { Header } from "@/components/layout/header";
import { useLanguage } from "@/context/language-context";
import type { CallLog, AgentConfig } from "@/types/database";

type CallWithAgent = CallLog & { agents_config: Pick<AgentConfig, "agent_name"> | null };

function formatDuration(secs: number | null) {
  if (!secs) return "—";
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

const STATUS_CONFIG = {
  completed: { text: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20", dot: "#10b981" },
  missed:    { text: "text-amber-400",   bg: "bg-amber-500/10",   border: "border-amber-500/20",   dot: "#f59e0b" },
  failed:    { text: "text-red-400",     bg: "bg-red-500/10",     border: "border-red-500/20",     dot: "#ef4444" },
} as const;

interface Props {
  calls: CallWithAgent[] | null;
  error: string | null;
}

export function CallsClientPage({ calls, error }: Props) {
  const { t } = useLanguage();

  const total     = calls?.length ?? 0;
  const completed = calls?.filter((c) => c.status === "completed").length ?? 0;
  const missed    = calls?.filter((c) => c.status === "missed").length ?? 0;

  const statusLabel = (status: string | null) => {
    switch (status) {
      case "completed": return t.status_completed;
      case "missed":    return t.status_missed;
      case "failed":    return t.status_failed;
      default:          return t.status_unknown;
    }
  };

  const statusIcon = (status: string | null) => {
    switch (status) {
      case "completed": return <CheckCircle className="w-3 h-3" />;
      case "missed":    return <AlertCircle className="w-3 h-3" />;
      case "failed":    return <XCircle className="w-3 h-3" />;
      default:          return <Phone className="w-3 h-3" />;
    }
  };

  return (
    <div className="flex-1 overflow-y-auto bg-surface-0">
      <Header title={t.page_calls_title} subtitle={t.page_calls_subtitle} />

      <div className="p-6 space-y-5">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-xl">
            {t.failed_load_calls} {error}
          </div>
        )}

        {/* KPI Row */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[
            { label: t.kpi_total_calls, value: total,     icon: Phone,       colorText: "text-brand-400",   colorBg: "bg-brand-500/10",   glow: "kpi-glow-violet" },
            { label: t.kpi_completed,   value: completed, icon: CheckCircle, colorText: "text-emerald-400", colorBg: "bg-emerald-500/10", glow: "kpi-glow-green" },
            { label: t.kpi_missed,      value: missed,    icon: AlertCircle, colorText: "text-amber-400",   colorBg: "bg-amber-500/10",   glow: "kpi-glow-amber" },
          ].map(({ label, value, icon: Icon, colorText, colorBg, glow }) => (
            <div key={label} className={`relative card p-5 flex items-center gap-4 overflow-hidden ${glow}`}>
              <div className={`w-9 h-9 rounded-xl ${colorBg} flex items-center justify-center flex-shrink-0`}>
                <Icon className={`w-4 h-4 ${colorText}`} />
              </div>
              <div>
                <p className="text-2xl font-extrabold text-white tracking-tight">{value}</p>
                <p className="text-gray-600 text-[11px]">{label}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Table */}
        {!calls?.length ? (
          <div className="card flex flex-col items-center justify-center py-24 text-center">
            <Phone className="w-8 h-8 text-gray-700 mb-3" />
            <p className="text-white font-medium">{t.no_calls_title}</p>
            <p className="text-gray-600 text-sm mt-1">{t.no_calls_desc}</p>
          </div>
        ) : (
          <div className="card overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  {[t.col_date, t.col_caller, t.col_agent, t.col_duration, t.col_status].map((h) => (
                    <th key={h} className="text-start text-[11px] text-gray-600 font-medium px-5 py-3">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {calls.map((call) => {
                  const cfg = STATUS_CONFIG[call.status as keyof typeof STATUS_CONFIG];
                  return (
                    <tr key={call.id} className="border-b border-border last:border-0 hover:bg-surface-2 transition-colors">
                      <td className="px-5 py-3.5 text-gray-400 text-[13px]">
                        {new Date(call.created_at).toLocaleString("he-IL", {
                          month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                        })}
                      </td>
                      <td className="px-4 py-3.5">
                        <div className="flex items-center gap-2">
                          <Phone className="w-3 h-3 text-gray-700" />
                          <span className="text-gray-300 text-[13px] font-mono">{call.phone_number ?? t.unknown_caller}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3.5 text-gray-500 text-[13px]">{call.agents_config?.agent_name ?? t.unknown_caller}</td>
                      <td className="px-4 py-3.5">
                        <div className="flex items-center gap-1.5 text-gray-500 text-[13px]">
                          <Clock className="w-3 h-3" />
                          {formatDuration(call.duration)}
                        </div>
                      </td>
                      <td className="px-4 py-3.5">
                        {cfg ? (
                          <span className={`inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full border ${cfg.text} ${cfg.bg} ${cfg.border}`}>
                            {statusIcon(call.status)}
                            {statusLabel(call.status)}
                          </span>
                        ) : (
                          <span className="text-gray-600 text-[11px]">{statusLabel(call.status)}</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
