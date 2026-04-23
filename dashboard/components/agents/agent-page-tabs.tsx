"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Archive } from "lucide-react";
import { AgentConfig } from "@/types/database";
import { AgentForm } from "./agent-form";
import { ClientAssetsTab } from "./client-assets-tab";
import { LiveVoicePanel } from "./live-voice-panel";
import { useLanguage } from "@/context/language-context";

interface Props {
  agent: AgentConfig;
}

type Tab = "settings" | "assets" | "voice";

export function AgentPageTabs({ agent }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("settings");
  const [archiving, setArchiving] = useState(false);
  const { t } = useLanguage();
  const router = useRouter();

  const handleArchive = async () => {
    if (!confirm(t.archive_confirm)) return;
    setArchiving(true);
    await fetch(`/api/agents/${agent.id}`, { method: "DELETE" });
    router.push("/dashboard/agents");
    router.refresh();
  };

  return (
    <div className="flex-1 overflow-y-auto" dir="rtl">
      {/* Tab bar */}
      <div className="sticky top-0 z-20 bg-surface-0/95 backdrop-blur border-b border-border px-8">
        <div className="flex items-center justify-between">
          <div className="flex gap-1 pt-2">
            <button
              onClick={() => setActiveTab("settings")}
              className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
                activeTab === "settings"
                  ? "text-white border-brand-600 bg-surface-2"
                  : "text-gray-500 border-transparent hover:text-gray-300"
              }`}
            >
              {t.tab_settings}
            </button>
            <button
              onClick={() => setActiveTab("assets")}
              className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
                activeTab === "assets"
                  ? "text-white border-brand-600 bg-surface-2"
                  : "text-gray-500 border-transparent hover:text-gray-300"
              }`}
            >
              {t.tab_assets}
            </button>
            <button
              onClick={() => setActiveTab("voice")}
              className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
                activeTab === "voice"
                  ? "text-white border-brand-600 bg-surface-2"
                  : "text-gray-500 border-transparent hover:text-gray-300"
              }`}
            >
              Live Voice
            </button>
          </div>
          <button
            onClick={handleArchive}
            disabled={archiving}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-red-400 px-3 py-1.5 rounded-lg hover:bg-red-500/10 transition-colors disabled:opacity-40"
          >
            <Archive className="w-3.5 h-3.5" />
            {archiving ? "..." : t.archive_agent_btn}
          </button>
        </div>
      </div>

      {/* Tab content */}
      {activeTab === "settings" && (
        <AgentForm agentId={agent.id} initial={agent} />
      )}
      {activeTab === "assets" && (
        <ClientAssetsTab clientId={agent.client_id ?? ""} />
      )}
      {activeTab === "voice" && (
        <LiveVoicePanel agentId={agent.id} />
      )}
    </div>
  );
}
