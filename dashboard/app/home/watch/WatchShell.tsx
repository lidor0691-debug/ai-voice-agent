"use client";

import { useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Watch } from "./Watch";
import { HomeShell } from "../_shared/HomeShell";
import type { WatchData } from "./watch-mock";
import { useLanguage } from "@/context/language-context";

/** Poll interval while the tab is visible. router.refresh() re-runs the
 *  server component which holds the internal key — browser never sees it. */
const POLL_MS = 12_000;

/** Trigger a server-component refresh every POLL_MS while the tab is
 *  visible; pause when hidden; resume with a single refresh on re-show.
 *  Overlap guard prevents stacking refreshes if a previous render is slow. */
function usePolledRefresh() {
  const router = useRouter();
  const inFlight = useRef(false);

  useEffect(() => {
    if (typeof document === "undefined") return;

    const safeRefresh = () => {
      if (inFlight.current) return;
      if (document.visibilityState !== "visible") return;
      inFlight.current = true;
      try {
        router.refresh();
      } finally {
        // router.refresh() returns synchronously; clear the guard on the
        // next tick so we don't stack two refreshes inside the same frame.
        setTimeout(() => { inFlight.current = false; }, 0);
      }
    };

    let intervalId: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      if (intervalId !== null) return;
      intervalId = setInterval(safeRefresh, POLL_MS);
    };
    const stop = () => {
      if (intervalId !== null) {
        clearInterval(intervalId);
        intervalId = null;
      }
    };

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        safeRefresh();   // single catch-up refresh on re-show
        start();
      } else {
        stop();
      }
    };

    if (document.visibilityState === "visible") start();
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      stop();
    };
  }, [router]);
}

interface WatchShellProps {
  // Required — the page is the single source of truth for which WatchData
  // shape to render (live mapping, quiet-live, fetch-failed, or explicit
  // dev demo). Removing the implicit `?? watchMock` fallback prevents fake
  // business activity from leaking into production on any failure path.
  initialData: WatchData;
}

export function WatchShell({ initialData }: WatchShellProps) {
  const { lang } = useLanguage();
  usePolledRefresh();

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
