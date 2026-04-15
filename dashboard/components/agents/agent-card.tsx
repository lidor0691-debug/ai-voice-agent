"use client";

import Link from "next/link";
import { Phone, Settings } from "lucide-react";
import { AgentConfig } from "@/types/database";
import { useLanguage } from "@/context/language-context";

interface Props { agent: AgentConfig; }

const GRADIENT_PAIRS = [
  ["from-brand-500","to-indigo-500"],
  ["from-blue-500","to-cyan-500"],
  ["from-emerald-500","to-teal-500"],
  ["from-amber-500","to-orange-500"],
  ["from-pink-500","to-rose-500"],
];

export function AgentCard({ agent }: Props) {
  const { t } = useLanguage();
  // deterministic color pick based on first char
  const idx = agent.agent_name.charCodeAt(0) % GRADIENT_PAIRS.length;
  const [from, to] = GRADIENT_PAIRS[idx];

  return (
    <Link
      href={`/dashboard/agents/${agent.id}`}
      className="group relative card p-5 hover:border-brand-500/30 transition-all overflow-hidden"
    >
      <div className="flex items-start justify-between mb-4">
        {/* Avatar */}
        <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${from} ${to} flex items-center justify-center shadow-glow-sm`}>
          <span className="text-white font-bold text-sm">{agent.agent_name.charAt(0).toUpperCase()}</span>
        </div>

        {/* Status badge */}
        <span
          className={`inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full border ${
            agent.is_active
              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
              : "bg-surface-3 text-gray-500 border-border"
          }`}
        >
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={agent.is_active ? { background:"#10b981", boxShadow:"0 0 6px #10b981" } : { background:"#334155" }}
          />
          {agent.is_active ? t.agent_active : t.agent_inactive}
        </span>
      </div>

      <h3 className="text-white font-semibold text-sm mb-1 group-hover:text-brand-400 transition-colors">
        {agent.agent_name}
      </h3>
      <p className="text-gray-600 text-[11px] mb-4 line-clamp-1">
        {[agent.language, agent.tone, agent.model_name].filter(Boolean).join(" · ") || t.not_configured}
      </p>

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-border">
        <div className="flex items-center gap-1.5 text-gray-600 text-[11px]">
          <Phone className="w-3 h-3" />
          <span>{agent.phone_number ?? t.no_number}</span>
        </div>
        <Settings className="w-3.5 h-3.5 text-gray-700 group-hover:text-brand-400 transition-colors" />
      </div>
    </Link>
  );
}
