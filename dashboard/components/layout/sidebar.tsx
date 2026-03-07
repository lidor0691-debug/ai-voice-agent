"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  BarChart3,
  Settings,
  PhoneCall,
  HelpCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", label: "לוח בקרה", icon: LayoutDashboard },
  { href: "/dashboard/leads", label: "פניות", icon: Users },
  { href: "/dashboard/analytics", label: "אנליטיקה", icon: BarChart3 },
  { href: "/dashboard/settings", label: "הגדרות", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-60 min-h-screen bg-slate-900 flex flex-col flex-shrink-0" dir="ltr">
      {/* Workspace label */}
      <div className="px-5 pt-4 pb-0">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-brand-500 select-none">
          Honda Demo Workspace
        </span>
      </div>

      {/* Brand */}
      <div className="h-14 flex items-center gap-3 px-5 mt-1 border-b border-slate-800">
        <div className="w-8 h-8 rounded-lg bg-brand-500 flex items-center justify-center flex-shrink-0">
          <PhoneCall className="w-4 h-4 text-white" />
        </div>
        <div>
          <p className="text-white font-semibold text-sm leading-none">Maya AI</p>
          <p className="text-slate-400 text-xs mt-0.5">Voice Assistant</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        <p className="text-slate-500 text-xs font-medium uppercase tracking-wider px-3 mb-3">
          ניווט
        </p>
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/dashboard"
              ? pathname === "/dashboard"
              : pathname.startsWith(href);

          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                active
                  ? "bg-brand-600 text-white"
                  : "text-slate-400 hover:text-white hover:bg-slate-800"
              )}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-3 py-4 border-t border-slate-800">
        <Link
          href="#"
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
        >
          <HelpCircle className="w-4 h-4" />
          עזרה ותמיכה
        </Link>
        <div className="flex items-center gap-3 px-3 py-2.5 mt-1">
          <div className="w-8 h-8 rounded-full bg-brand-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
            מ
          </div>
          <div className="overflow-hidden">
            <p className="text-slate-300 text-xs font-medium truncate">מנהל מערכת</p>
            <p className="text-slate-500 text-xs truncate">admin@maya-ai.com</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
