"use client";

import { useState } from "react";
import { AgentConfig } from "@/types/database";
import { AgentForm } from "./agent-form";
import { ClientAssetsTab } from "./client-assets-tab";

interface Props {
  agent: AgentConfig;
}

type Tab = "settings" | "assets";

export function AgentPageTabs({ agent }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("settings");

  return (
    <div className="flex-1 overflow-y-auto" dir="rtl">
      {/* Tab bar */}
      <div className="sticky top-0 z-20 bg-surface-0/95 backdrop-blur border-b border-border px-8">
        <div className="flex gap-1 pt-2">
          <button
            onClick={() => setActiveTab("settings")}
            className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
              activeTab === "settings"
                ? "text-white border-brand-600 bg-surface-2"
                : "text-gray-500 border-transparent hover:text-gray-300"
            }`}
          >
            הגדרות נציגה
          </button>
          <button
            onClick={() => setActiveTab("assets")}
            className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
              activeTab === "assets"
                ? "text-white border-brand-600 bg-surface-2"
                : "text-gray-500 border-transparent hover:text-gray-300"
            }`}
          >
            נכסי לקוח
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
    </div>
  );
}
