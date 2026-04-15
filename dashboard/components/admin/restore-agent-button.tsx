"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { RotateCcw } from "lucide-react";

export function RestoreAgentButton({ agentId }: { agentId: string }) {
  const [restoring, setRestoring] = useState(false);
  const router = useRouter();

  const handleRestore = async () => {
    setRestoring(true);
    await fetch(`/api/agents/${agentId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: true }),
    });
    router.refresh();
  };

  return (
    <button
      onClick={handleRestore}
      disabled={restoring}
      className="flex items-center gap-1.5 text-xs text-emerald-400 hover:text-emerald-300 px-2.5 py-1.5 rounded-lg hover:bg-emerald-500/10 transition-colors disabled:opacity-40"
    >
      <RotateCcw className="w-3.5 h-3.5" />
      {restoring ? "..." : "Restore"}
    </button>
  );
}
