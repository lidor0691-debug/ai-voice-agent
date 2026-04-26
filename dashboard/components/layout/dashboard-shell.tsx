"use client";

import { createContext, useContext, useState, useCallback } from "react";
import { LanguageProvider, useLanguage } from "@/context/language-context";
import { Sidebar } from "@/components/layout/sidebar";
import { DashboardAssistant } from "@/components/dashboard/dashboard-assistant";

interface SidebarCtx {
  open: boolean;
  toggle: () => void;
  close: () => void;
}
const SidebarContext = createContext<SidebarCtx>({ open: false, toggle: () => {}, close: () => {} });
export const useSidebar = () => useContext(SidebarContext);

interface ShellProps {
  children: React.ReactNode;
  isAdmin: boolean;
  defaultAgentId?: string | null;
}

function ShellInner({ children, isAdmin, defaultAgentId }: ShellProps) {
  const { lang } = useLanguage();
  const [open, setOpen] = useState(false);
  const toggle = useCallback(() => setOpen((o) => !o), []);
  const close = useCallback(() => setOpen(false), []);

  return (
    <SidebarContext.Provider value={{ open, toggle, close }}>
      <div
        dir={lang === "he" ? "rtl" : "ltr"}
        className="flex h-screen overflow-hidden bg-surface-0"
      >
        {/* Desktop sidebar */}
        <div className="hidden md:block">
          <Sidebar isAdmin={isAdmin} />
        </div>

        {/* Mobile drawer */}
        <div className={`sidebar-drawer md:hidden bg-surface-1 border-e border-border ${open ? "open" : ""}`}>
          <Sidebar isAdmin={isAdmin} onNavigate={close} />
        </div>

        {/* Backdrop */}
        {open && (
          <div className="sidebar-backdrop md:hidden" onClick={close} />
        )}

        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {children}
        </div>
        <DashboardAssistant defaultAgentId={defaultAgentId ?? null} />
      </div>
    </SidebarContext.Provider>
  );
}

export function DashboardShell({ children, isAdmin, defaultAgentId }: ShellProps) {
  return (
    <LanguageProvider>
      <ShellInner isAdmin={isAdmin} defaultAgentId={defaultAgentId}>{children}</ShellInner>
    </LanguageProvider>
  );
}
