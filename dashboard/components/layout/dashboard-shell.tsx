"use client";

import { LanguageProvider, useLanguage } from "@/context/language-context";
import { Sidebar } from "@/components/layout/sidebar";
import { DashboardAssistant } from "@/components/dashboard/dashboard-assistant";

interface ShellProps {
  children: React.ReactNode;
  isAdmin: boolean;
  defaultAgentId?: string | null;
}

function ShellInner({ children, isAdmin, defaultAgentId }: ShellProps) {
  const { lang } = useLanguage();
  return (
    <div
      dir={lang === "he" ? "rtl" : "ltr"}
      className="flex h-screen overflow-hidden bg-surface-0"
    >
      <Sidebar isAdmin={isAdmin} />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {children}
      </div>
      <DashboardAssistant defaultAgentId={defaultAgentId ?? null} />
    </div>
  );
}

export function DashboardShell({ children, isAdmin, defaultAgentId }: ShellProps) {
  return (
    <LanguageProvider>
      <ShellInner isAdmin={isAdmin} defaultAgentId={defaultAgentId}>{children}</ShellInner>
    </LanguageProvider>
  );
}
