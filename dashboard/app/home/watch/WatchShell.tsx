"use client";

import { useCallback } from "react";
import { Watch } from "./Watch";
import { HomeShell } from "../_shared/HomeShell";
import type { WatchData } from "./watch-mock";
import { useLanguage } from "@/context/language-context";

interface WatchShellProps {
  // Required — the page is the single source of truth for which WatchData
  // shape to render (live mapping, quiet-live, fetch-failed, or explicit
  // dev demo). Removing the implicit `?? watchMock` fallback prevents fake
  // business activity from leaking into production on any failure path.
  initialData: WatchData;
}

export function WatchShell({ initialData }: WatchShellProps) {
  const { lang } = useLanguage();

  // Pass the prop straight through — never wrap it in useState. router.refresh()
  // re-runs page.tsx server-side and feeds a new initialData to this client
  // component; useState would freeze the first value and ignore subsequent
  // server-rendered updates, breaking the post-action hero swap.
  const data = initialData;

  const handleApprove = useCallback(() => {
    console.log("[Maya] approved:", data.hero.target);
  }, [data.hero.target]);

  const handleDecline = useCallback(() => {
    console.log("[Maya] declined:", data.hero.target);
  }, [data.hero.target]);

  const handleAsk = useCallback((text: string) => {
    console.log("[Maya] ask:", text);
  }, []);

  return (
    <HomeShell lang={lang}>
      <Watch
        data={data}
        lang={lang}
        onApprove={handleApprove}
        onDecline={handleDecline}
        onAsk={handleAsk}
      />
    </HomeShell>
  );
}
