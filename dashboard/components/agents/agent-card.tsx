import Link from "next/link";
import { Phone, Settings, Circle } from "lucide-react";
import { AgentConfig } from "@/types/database";

interface Props {
  agent: AgentConfig;
}

export function AgentCard({ agent }: Props) {
  return (
    <Link
      href={`/dashboard/agents/${agent.id}`}
      className="group block bg-surface-2 border border-border rounded-xl p-5 hover:border-brand-600/40 hover:bg-surface-3 transition-all"
    >
      {/* Top row */}
      <div className="flex items-start justify-between mb-4">
        <div className="w-10 h-10 rounded-xl bg-brand-600/15 border border-brand-600/20 flex items-center justify-center">
          <span className="text-brand-400 font-bold text-sm">
            {agent.agent_name.charAt(0).toUpperCase()}
          </span>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${
            agent.is_active
              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
              : "bg-gray-500/10 text-gray-400 border border-gray-500/20"
          }`}
        >
          <Circle className={`w-1.5 h-1.5 fill-current ${agent.is_active ? "text-emerald-400" : "text-gray-500"}`} />
          {agent.is_active ? "Active" : "Inactive"}
        </span>
      </div>

      {/* Name */}
      <h3 className="text-white font-medium text-sm mb-1 group-hover:text-brand-400 transition-colors">
        {agent.agent_name}
      </h3>

      {/* Language + tone */}
      <p className="text-gray-500 text-xs mb-4 line-clamp-1">
        {[agent.language, agent.tone, agent.model_name].filter(Boolean).join(" · ") || "Not configured"}
      </p>

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-border">
        <div className="flex items-center gap-1.5 text-gray-500 text-xs">
          <Phone className="w-3 h-3" />
          <span>{agent.phone_number ?? "No number"}</span>
        </div>
        <Settings className="w-3.5 h-3.5 text-gray-600 group-hover:text-brand-500 transition-colors" />
      </div>
    </Link>
  );
}
