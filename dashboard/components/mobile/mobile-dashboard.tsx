"use client";

import { useState, useCallback } from "react";
import { MobileKpiStrip } from "./mobile-kpi-strip";
import { MobilePriorities } from "./mobile-priorities";
import { MobileLeadList } from "./mobile-lead-list";
import { MayaFab } from "./maya-fab";
import type { AgentConfig, CallLog } from "@/types/database";

interface Props {
  agents: Pick<AgentConfig, "id" | "agent_name" | "is_active" | "system_prompt" | "first_message" | "phone_number">[] | null;
  calls: Pick<CallLog, "id" | "status" | "created_at">[] | null;
  defaultAgentId: string | null;
}

export function MobileDashboard({ agents, calls, defaultAgentId }: Props) {
  const activeAgents = agents?.filter((a) => a.is_active).length ?? 0;
  const totalCalls = calls?.length ?? 0;
  const [openPriorities, setOpenPriorities] = useState(0);

  const handleCountChange = useCallback((count: number) => {
    setOpenPriorities(count);
  }, []);

  return (
    <>
      <div className="p-4 space-y-4 bg-surface-0 min-h-full">
        {/* KPI Strip */}
        <MobileKpiStrip
          activeAgents={activeAgents}
          totalCalls={totalCalls}
          openPriorities={openPriorities}
        />

        {/* Hero: Today's Priorities */}
        <MobilePriorities
          agentId={agents?.[0]?.id}
          onCountChange={handleCountChange}
        />

        {/* Recent Leads */}
        <MobileLeadList />

        {/* Bottom spacer for FAB clearance */}
        <div className="h-20" />
      </div>

      {/* Maya Voice FAB — fixed, outside scroll */}
      <MayaFab agentId={defaultAgentId} />
    </>
  );
}
