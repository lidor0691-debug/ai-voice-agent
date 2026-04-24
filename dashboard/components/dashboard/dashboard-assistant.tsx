"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { LiveVoicePanel } from "../agents/live-voice-panel";
import { ActionCard, type ActionProposal } from "./action-card";

const ROUTES: Record<string, string> = {
  dashboard: "/dashboard",
  leads: "/dashboard/leads",
  calls: "/dashboard/calls",
  agents: "/dashboard/agents",
  knowledge: "/dashboard/knowledge",
};

interface Props {
  defaultAgentId: string | null;
}

export function DashboardAssistant({ defaultAgentId }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const pathnameRef = useRef(pathname);
  pathnameRef.current = pathname;
  const [activeProposal, setActiveProposal] = useState<ActionProposal | null>(null);

  const handleActionProposal = useCallback(
    (proposal: ActionProposal) => {
      setActiveProposal(proposal);
    },
    [],
  );

  const handleUiAction = useCallback(
    (action: string, target: string, extra?: Record<string, string>) => {
      console.log("[Assistant] handleUiAction:", action, target, extra);
      if (action === "open_tab") {
        const path = ROUTES[target];
        if (path) {
          router.push(path);
        }
      } else if (action === "open_agent") {
        const tab = extra?.tab;
        const path = tab && tab !== "settings"
          ? `/dashboard/agents/${target}?tab=${tab}`
          : `/dashboard/agents/${target}`;
        router.push(path);
      }
      // Future: open_section, scroll_to, highlight_metric
    },
    [router],
  );

  if (!defaultAgentId) return null;

  return (
    <div className="fixed bottom-6 left-6 z-50 w-80 card p-4 shadow-2xl border border-border/50 rounded-2xl bg-surface-1/95 backdrop-blur">
      <LiveVoicePanel
        agentId={defaultAgentId}
        mode="assistant"
        onUiAction={handleUiAction}
        onActionProposal={handleActionProposal}
      />
      {activeProposal && (
        <ActionCard
          proposal={activeProposal}
          onDismiss={() => setActiveProposal(null)}
        />
      )}
    </div>
  );
}
