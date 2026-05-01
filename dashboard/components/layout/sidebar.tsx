"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  LayoutDashboard, Bot, Phone, BookOpen,
  Settings, Zap, Users, ShieldCheck, LogOut, Eye,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/context/language-context";
import { createSupabaseBrowserClient } from "@/lib/supabase-browser";

export function Sidebar({ isAdmin = false, onNavigate, compact = false }: { isAdmin?: boolean; onNavigate?: () => void; compact?: boolean }) {
  const pathname = usePathname();
  const router = useRouter();
  const { t } = useLanguage();
  const supabase = createSupabaseBrowserClient();
  const [userEmail, setUserEmail] = useState<string | null>(null);

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => {
      setUserEmail(data.user?.email ?? null);
    });
  }, []);

  async function handleLogout() {
    await supabase.auth.signOut();
    router.push("/login");
  }

  const NAV_ITEMS = [
    { href: "/dashboard",           label: t.nav_dashboard, icon: LayoutDashboard },
    { href: "/dashboard/agents",    label: t.nav_agents,    icon: Bot },
    { href: "/dashboard/calls",     label: t.nav_calls,     icon: Phone },
    { href: "/dashboard/leads",     label: t.nav_leads,     icon: Users },
    { href: "/dashboard/knowledge", label: t.nav_knowledge, icon: BookOpen },
    { href: "/dashboard/settings",  label: t.nav_settings,  icon: Settings },
  ];

  const MOBILE_HREFS = ["/dashboard", "/dashboard/agents", "/dashboard/calls", "/dashboard/leads"];
  const visibleItems = compact ? NAV_ITEMS.filter((item) => MOBILE_HREFS.includes(item.href)) : NAV_ITEMS;

  return (
    <aside className="w-56 h-full bg-surface-1 border-e border-border flex flex-col flex-shrink-0">
      {/* Brand */}
      <div className="h-14 flex items-center gap-3 px-4 border-b border-border">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500 to-indigo-500 flex items-center justify-center flex-shrink-0 shadow-glow-sm">
          <Zap className="w-3.5 h-3.5 text-white" />
        </div>
        <div>
          <p className="text-white font-bold text-sm leading-none tracking-tight">
            Maya<span className="text-brand-400">AI</span>
          </p>
          <p className="text-gray-600 text-[10px] mt-0.5">Agent Platform</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-3 space-y-0.5">
        {visibleItems.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/dashboard"
              ? pathname === "/dashboard"
              : pathname.startsWith(href);

          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              className={cn(
                "relative flex items-center gap-2.5 px-3 py-2 rounded-xl text-[13px] font-medium transition-all",
                active
                  ? "bg-brand-500/10 text-white border border-brand-500/20"
                  : "text-gray-500 hover:text-gray-200 hover:bg-surface-3"
              )}
            >
              {active && (
                <span className="absolute end-0 top-1/2 -translate-y-1/2 w-0.5 h-4 rounded-full bg-gradient-to-b from-brand-500 to-indigo-500" />
              )}
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Admin links */}
      {isAdmin && (
        <div className="px-2 pb-2 space-y-0.5">
          <Link
            href="/admin"
            onClick={onNavigate}
            className={cn(
              "relative flex items-center gap-2.5 px-3 py-2 rounded-xl text-[13px] font-medium transition-all",
              pathname.startsWith("/admin")
                ? "bg-brand-500/10 text-white border border-brand-500/20"
                : "text-gray-500 hover:text-gray-200 hover:bg-surface-3"
            )}
          >
            {pathname.startsWith("/admin") && (
              <span className="absolute end-0 top-1/2 -translate-y-1/2 w-0.5 h-4 rounded-full bg-gradient-to-b from-brand-500 to-indigo-500" />
            )}
            <ShieldCheck className="w-4 h-4 flex-shrink-0" />
            Admin
          </Link>
          <Link
            href="/dashboard/admin/maya-watch"
            onClick={onNavigate}
            className={cn(
              "relative flex items-center gap-2.5 px-3 py-2 rounded-xl text-[13px] font-medium transition-all",
              pathname === "/dashboard/admin/maya-watch"
                ? "bg-brand-500/10 text-white border border-brand-500/20"
                : "text-gray-500 hover:text-gray-200 hover:bg-surface-3"
            )}
          >
            {pathname === "/dashboard/admin/maya-watch" && (
              <span className="absolute end-0 top-1/2 -translate-y-1/2 w-0.5 h-4 rounded-full bg-gradient-to-b from-brand-500 to-indigo-500" />
            )}
            <Eye className="w-4 h-4 flex-shrink-0" />
            Maya Watch
          </Link>
        </div>
      )}

      {/* Account footer */}
      <div className="px-3 pb-3 pt-2 border-t border-border">
        <div className="rounded-xl bg-surface-2 border border-border overflow-hidden">
          {/* User row */}
          <div className="flex items-center gap-2.5 px-3 py-2.5">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500 to-indigo-500 flex items-center justify-center text-white text-[11px] font-bold flex-shrink-0">
              {userEmail ? userEmail[0].toUpperCase() : "U"}
            </div>
            <div className="overflow-hidden flex-1 min-w-0">
              <p className="text-gray-200 text-[12px] font-medium truncate leading-none">
                {userEmail ?? "User"}
              </p>
              {isAdmin && (
                <p className="text-brand-400 text-[10px] mt-0.5 leading-none">Admin</p>
              )}
            </div>
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 flex-shrink-0" style={{boxShadow:'0 0 6px #10b981'}} />
          </div>
          {/* Logout row */}
          <div className="border-t border-border">
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-2 px-3 py-2 text-[12px] font-medium text-red-400 hover:bg-red-500/10 transition-colors"
            >
              <LogOut className="w-3.5 h-3.5 flex-shrink-0" />
              {t.logout ?? "Logout"}
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
}
