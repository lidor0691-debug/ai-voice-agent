"use client";

import { useState, useCallback } from "react";
import { Mic, X } from "lucide-react";
import { LiveVoicePanel } from "@/components/agents/live-voice-panel";
import { ActionCard, type ActionProposal } from "@/components/dashboard/action-card";

interface Props {
  agentId: string | null;
}

export function MayaFab({ agentId }: Props) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const [activeProposal, setActiveProposal] = useState<ActionProposal | null>(null);

  const handleActionProposal = useCallback((proposal: ActionProposal) => {
    setActiveProposal(proposal);
  }, []);

  if (!agentId) return null;

  return (
    <>
      {/* FAB button — fixed bottom-left */}
      {!sheetOpen && (
        <button
          onClick={() => setSheetOpen(true)}
          className="fixed bottom-6 left-4 z-50 w-14 h-14 rounded-full bg-gradient-to-br from-brand-500 to-indigo-500 flex items-center justify-center shadow-lg hover:shadow-xl transition-shadow"
          style={{ boxShadow: "0 4px 20px rgba(139,92,246,0.4)" }}
          aria-label="Talk to Maya"
        >
          <Mic className="w-6 h-6 text-white" />
        </button>
      )}

      {/* Bottom sheet overlay */}
      {sheetOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-50 bg-black/50"
            onClick={() => setSheetOpen(false)}
          />

          {/* Sheet */}
          <div className="fixed bottom-0 left-0 right-0 z-50 bg-surface-1 border-t border-border rounded-t-2xl" dir="rtl">
            {/* Sheet header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-brand-500 to-indigo-500 flex items-center justify-center">
                  <Mic className="w-3 h-3 text-white" />
                </div>
                <span className="text-white text-sm font-medium">דבר עם מאיה</span>
              </div>
              <button
                onClick={() => setSheetOpen(false)}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-white hover:bg-surface-3 transition-colors"
                aria-label="Close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Voice panel — constrained height, override inner padding */}
            <div className="max-h-[40vh] overflow-y-auto [&>div]:p-4 [&>div]:py-4 [&>div>div]:max-w-none">
              <LiveVoicePanel
                agentId={agentId}
                mode="assistant"
                onActionProposal={handleActionProposal}
              />
            </div>

            {/* ActionCard overlay if Maya proposes an action */}
            {activeProposal && (
              <div className="px-4 pb-4">
                <ActionCard
                  proposal={activeProposal}
                  onDismiss={() => setActiveProposal(null)}
                />
              </div>
            )}
          </div>
        </>
      )}
    </>
  );
}
