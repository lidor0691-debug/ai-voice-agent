"use client";

import Link from "next/link";
import { Plus } from "lucide-react";
import { AgentCard } from "@/components/agents/agent-card";
import { useLanguage } from "@/context/language-context";
import type { AgentConfig } from "@/types/database";

interface Props {
  agents: AgentConfig[] | null;
  error: string | null;
}

export function AgentsClientPage({ agents, error }: Props) {
  const { t } = useLanguage();
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="sticky top-0 z-10 bg-surface-0/80 backdrop-blur border-b border-border px-8 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-white font-semibold text-lg">{t.page_agents_title}</h1>
          <p className="text-gray-500 text-sm mt-0.5">{agents?.length ?? 0}</p>
        </div>
        <Link
          href="/dashboard/agents/new"
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          {t.new_agent_btn}
        </Link>
      </div>

      <div className="p-8">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-lg mb-6">
            {t.failed_load_agents} {error}
          </div>
        )}

        {!agents?.length && !error ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-12 h-12 rounded-2xl bg-surface-2 border border-border flex items-center justify-center mb-4">
              <Plus className="w-5 h-5 text-gray-500" />
            </div>
            <p className="text-white font-medium">{t.no_agents_title}</p>
            <p className="text-gray-500 text-sm mt-1 mb-6">{t.no_agents_desc}</p>
            <Link
              href="/dashboard/agents/new"
              className="bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              {t.create_agent_btn}
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {agents?.map((agent) => <AgentCard key={agent.id} agent={agent} />)}
          </div>
        )}
      </div>
    </div>
  );
}
