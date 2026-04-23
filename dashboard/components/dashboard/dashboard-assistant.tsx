"use client";

import { useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { LiveVoicePanel } from "../agents/live-voice-panel";

interface Props {
  defaultAgentId: string | null;
}

export function DashboardAssistant({ defaultAgentId }: Props) {
  const router = useRouter();
  const pathname = usePathname();

  const handleUiAction = useCallback(
    (action: string, target: string) => {
      if (action === "open_tab") {
        const routes: Record<string, string> = {
          leads: "/dashboard/leads",
          calls: "/dashboard/calls",
          agents: "/dashboard/agents",
          knowledge: "/dashboard/knowledge",
        };
        const path = routes[target];
        if (path && path !== pathname) router.push(path);
      }
      // Future: open_section, scroll_to, highlight_metric
    },
    [router, pathname],
  );

  if (!defaultAgentId) return null;

  return (
    <div className="card p-4">
      <LiveVoicePanel
        agentId={defaultAgentId}
        mode="assistant"
        onUiAction={handleUiAction}
      />
    </div>
  );
}
