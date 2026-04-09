import Link from "next/link";
import { Plus } from "lucide-react";
import { supabase } from "@/lib/supabase";
import { AgentConfig } from "@/types/database";
import { AgentCard } from "@/components/agents/agent-card";

export const dynamic = "force-dynamic";

export default async function AgentsPage() {
  const { data, error } = await supabase
    .from("agents_config")
    .select("*")
    .order("created_at", { ascending: false });

  const agents = data as AgentConfig[] | null;

  return (
    <div className="flex-1 overflow-y-auto">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-surface-0/80 backdrop-blur border-b border-border px-8 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-white font-semibold text-lg">Agents</h1>
          <p className="text-gray-500 text-sm mt-0.5">
            {agents?.length ?? 0} agent{agents?.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Link
          href="/dashboard/agents/new"
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Agent
        </Link>
      </div>

      <div className="p-8">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-lg mb-6">
            Failed to load agents: {error.message}
          </div>
        )}

        {!agents?.length && !error ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-12 h-12 rounded-2xl bg-surface-2 border border-border flex items-center justify-center mb-4">
              <Plus className="w-5 h-5 text-gray-500" />
            </div>
            <p className="text-white font-medium">No agents yet</p>
            <p className="text-gray-500 text-sm mt-1 mb-6">
              Create your first AI voice agent to get started
            </p>
            <Link
              href="/dashboard/agents/new"
              className="bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              Create Agent
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {agents?.map((agent) => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
