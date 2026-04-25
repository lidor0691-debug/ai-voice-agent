"use client";

import Link from "next/link";
import { Plus } from "lucide-react";
import { AgentCard } from "@/components/agents/agent-card";
import { Header } from "@/components/layout/header";
import { useLanguage } from "@/context/language-context";
import type { AgentConfig } from "@/types/database";

interface Props {
  agents: AgentConfig[] | null;
  error: string | null;
  isAdmin?: boolean;
}

export function AgentsClientPage({ agents, error, isAdmin = false }: Props) {
  const { t } = useLanguage();

  const action = isAdmin ? (
    <Link href="/dashboard/agents/new" className="btn-primary flex items-center gap-2">
      <Plus className="w-3.5 h-3.5" />
      {t.new_agent_btn}
    </Link>
  ) : null;

  return (
    <div className="flex-1 overflow-y-auto bg-surface-0">
      <Header
        title={t.page_agents_title}
        subtitle={`${agents?.length ?? 0} agents`}
        action={action}
      />

      <div className="p-6">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-xl mb-6">
            {t.failed_load_agents} {error}
          </div>
        )}

        {!agents?.length && !error ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-12 h-12 rounded-2xl card flex items-center justify-center mb-4">
              <Plus className="w-5 h-5 text-gray-600" />
            </div>
            <p className="text-white font-medium">{t.no_agents_title}</p>
            <p className="text-gray-600 text-sm mt-1 mb-6">{t.no_agents_desc}</p>
            {isAdmin && (
              <Link href="/dashboard/agents/new" className="btn-primary">
                {t.create_agent_btn}
              </Link>
            )}
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
