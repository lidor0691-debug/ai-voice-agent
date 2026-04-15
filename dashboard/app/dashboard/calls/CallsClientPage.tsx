"use client";

import { Phone, Clock, CheckCircle, XCircle, AlertCircle } from "lucide-react";
import { useLanguage } from "@/context/language-context";
import type { CallLog, AgentConfig } from "@/types/database";

type CallWithAgent = CallLog & { agents_config: Pick<AgentConfig, "agent_name"> | null };

function formatDuration(secs: number | null) {
  if (!secs) return "—";
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function statusStyle(status: string | null) {
  switch (status) {
    case "completed": return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
    case "missed":    return "bg-amber-500/10 text-amber-400 border-amber-500/20";
    case "failed":    return "bg-red-500/10 text-red-400 border-red-500/20";
    default:          return "bg-gray-500/10 text-gray-400 border-gray-500/20";
  }
}

function statusIcon(status: string | null) {
  switch (status) {
    case "completed": return <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />;
    case "missed":    return <AlertCircle className="w-3.5 h-3.5 text-amber-400" />;
    case "failed":    return <XCircle className="w-3.5 h-3.5 text-red-400" />;
    default:          return <Phone className="w-3.5 h-3.5 text-gray-500" />;
  }
}

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

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="sticky top-0 z-10 bg-surface-0/80 backdrop-blur border-b border-border px-8 py-4">
        <h1 className="text-white font-semibold text-lg">{t.page_calls_title}</h1>
        <p className="text-gray-500 text-sm mt-0.5">{t.page_calls_subtitle}</p>
      </div>

      <div className="p-8 space-y-6">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-lg">
            {t.failed_load_calls} {error}
          </div>
        )}

        <div className="grid grid-cols-3 gap-4">
          {[
            { label: t.kpi_total_calls, value: total,     icon: Phone,       color: "text-brand-400",   bg: "bg-brand-600/10" },
            { label: t.kpi_completed,   value: completed, icon: CheckCircle, color: "text-emerald-400", bg: "bg-emerald-500/10" },
            { label: t.kpi_missed,      value: missed,    icon: AlertCircle, color: "text-amber-400",   bg: "bg-amber-500/10" },
          ].map(({ label, value, icon: Icon, color, bg }) => (
            <div key={label} className="bg-surface-2 border border-border rounded-xl p-5 flex items-center gap-4">
              <div className={`w-10 h-10 rounded-xl ${bg} flex items-center justify-center flex-shrink-0`}>
                <Icon className={`w-5 h-5 ${color}`} />
              </div>
              <div>
                <p className="text-2xl font-bold text-white">{value}</p>
                <p className="text-gray-500 text-xs">{label}</p>
              </div>
            </div>
          ))}
        </div>

        {!calls?.length ? (
          <div className="flex flex-col items-center justify-center py-24 text-center bg-surface-2 border border-border rounded-xl">
            <Phone className="w-8 h-8 text-gray-600 mb-3" />
            <p className="text-white font-medium">{t.no_calls_title}</p>
            <p className="text-gray-500 text-sm mt-1">{t.no_calls_desc}</p>
          </div>
        ) : (
          <div className="bg-surface-2 border border-border rounded-xl overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-start text-xs text-gray-500 font-medium px-5 py-3">{t.col_date}</th>
                  <th className="text-start text-xs text-gray-500 font-medium px-4 py-3">{t.col_caller}</th>
                  <th className="text-start text-xs text-gray-500 font-medium px-4 py-3">{t.col_agent}</th>
                  <th className="text-start text-xs text-gray-500 font-medium px-4 py-3">{t.col_duration}</th>
                  <th className="text-start text-xs text-gray-500 font-medium px-4 py-3">{t.col_status}</th>
                </tr>
              </thead>
              <tbody>
                {calls.map((call) => (
                  <tr key={call.id} className="border-b border-border last:border-0 hover:bg-surface-3 transition-colors">
                    <td className="px-5 py-3.5 text-gray-300 text-sm">
                      {new Date(call.created_at).toLocaleString("he-IL", {
                        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                      })}
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-2">
                        <Phone className="w-3 h-3 text-gray-600" />
                        <span className="text-gray-300 text-sm font-mono">{call.phone_number ?? t.unknown_caller}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3.5 text-gray-400 text-sm">{call.agents_config?.agent_name ?? t.unknown_caller}</td>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-1.5 text-gray-400 text-sm">
                        <Clock className="w-3 h-3" />
                        {formatDuration(call.duration)}
                      </div>
                    </td>
                    <td className="px-4 py-3.5">
                      <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border ${statusStyle(call.status)}`}>
                        {statusIcon(call.status)}
                        {statusLabel(call.status)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
