"use client";

import { LanguageProvider, useLanguage } from "@/context/language-context";
import { Sidebar } from "@/components/layout/sidebar";

function ShellInner({ children, isAdmin }: { children: React.ReactNode; isAdmin: boolean }) {
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
    </div>
  );
}

export function DashboardShell({ children, isAdmin }: { children: React.ReactNode; isAdmin: boolean }) {
  return (
    <LanguageProvider>
      <ShellInner isAdmin={isAdmin}>{children}</ShellInner>
    </LanguageProvider>
  );
}
