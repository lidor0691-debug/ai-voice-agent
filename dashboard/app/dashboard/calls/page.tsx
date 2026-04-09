import { supabase } from "@/lib/supabase";
import { CallLog, AgentConfig } from "@/types/database";
import { Phone, Clock, CheckCircle, XCircle, AlertCircle } from "lucide-react";

export const dynamic = "force-dynamic";

type CallWithAgent = CallLog & { agents_config: Pick<AgentConfig, "agent_name"> | null };

function statusIcon(status: string | null) {
  switch (status) {
    case "completed": return <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />;
    case "missed":    return <AlertCircle className="w-3.5 h-3.5 text-amber-400" />;
    case "failed":    return <XCircle className="w-3.5 h-3.5 text-red-400" />;
    default:          return <Phone className="w-3.5 h-3.5 text-gray-500" />;
  }
}

function statusStyle(status: string | null) {
  switch (status) {
    case "completed": return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
    case "missed":    return "bg-amber-500/10 text-amber-400 border-amber-500/20";
    case "failed":    return "bg-red-500/10 text-red-400 border-red-500/20";
    default:          return "bg-gray-500/10 text-gray-400 border-gray-500/20";
  }
}

function formatDuration(secs: number | null) {
  if (!secs) return "—";
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

export default async function CallsPage() {
  const { data, error } = await supabase
    .from("call_logs")
    .select("*, agents_config(agent_name)")
    .order("created_at", { ascending: false })
    .limit(100);

  const calls = data as CallWithAgent[] | null;

  const total = calls?.length ?? 0;
  const completed = calls?.filter((c) => c.status === "completed").length ?? 0;
  const missed = calls?.filter((c) => c.status === "missed").length ?? 0;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="sticky top-0 z-10 bg-surface-0/80 backdrop-blur border-b border-border px-8 py-4">
        <h1 className="text-white font-semibold text-lg">Call Logs</h1>
        <p className="text-gray-500 text-sm mt-0.5">Recent calls across all agents</p>
      </div>

      <div className="p-8 space-y-6">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-lg">
            Failed to load calls: {error.message}
          </div>
        )}

        {/* Quick stats */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Total Calls",  value: total,     icon: Phone,        color: "text-brand-400",   bg: "bg-brand-600/10" },
            { label: "Completed",    value: completed, icon: CheckCircle,  color: "text-emerald-400", bg: "bg-emerald-500/10" },
            { label: "Missed",       value: missed,    icon: AlertCircle,  color: "text-amber-400",   bg: "bg-amber-500/10" },
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
            <p className="text-white font-medium">No calls yet</p>
            <p className="text-gray-500 text-sm mt-1">
              Calls will appear here once your agents start receiving them
            </p>
          </div>
        ) : (
          <div className="bg-surface-2 border border-border rounded-xl overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-xs text-gray-500 font-medium px-5 py-3">Date</th>
                  <th className="text-left text-xs text-gray-500 font-medium px-4 py-3">Caller</th>
                  <th className="text-left text-xs text-gray-500 font-medium px-4 py-3">Agent</th>
                  <th className="text-left text-xs text-gray-500 font-medium px-4 py-3">Duration</th>
                  <th className="text-left text-xs text-gray-500 font-medium px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {calls.map((call) => (
                  <tr key={call.id} className="border-b border-border last:border-0 hover:bg-surface-3 transition-colors">
                    <td className="px-5 py-3.5 text-gray-300 text-sm">
                      {new Date(call.created_at).toLocaleString("en-US", {
                        month: "short", day: "numeric",
                        hour: "2-digit", minute: "2-digit",
                      })}
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-2">
                        <Phone className="w-3 h-3 text-gray-600" />
                        <span className="text-gray-300 text-sm font-mono">
                          {call.phone_number ?? "Unknown"}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3.5 text-gray-400 text-sm">
                      {call.agents_config?.agent_name ?? "Unknown"}
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-1.5 text-gray-400 text-sm">
                        <Clock className="w-3 h-3" />
                        {formatDuration(call.duration)}
                      </div>
                    </td>
                    <td className="px-4 py-3.5">
                      <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border ${statusStyle(call.status)}`}>
                        {statusIcon(call.status)}
                        {call.status ?? "unknown"}
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
