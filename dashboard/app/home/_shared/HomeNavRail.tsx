"use client";

import Link from "next/link";
import { Activity, Phone, MessageCircle, Users, Sparkles, Bot, Zap, BarChart3, Settings } from "lucide-react";
import { homeStrings, NAV_ORDER, type HomeNavKey, type Lang } from "./home-strings";

const ICONS: Record<HomeNavKey, React.ComponentType<{ size?: number }>> = {
  watch:    Activity,
  calls:    Phone,
  whatsapp: MessageCircle,
  leads:    Users,
  insights: Sparkles,
  agents:   Bot,
  automate: Zap,
  reports:  BarChart3,
  settings: Settings,
};

interface HomeNavRailProps {
  lang: Lang;
  active: HomeNavKey;
  user: { name: string; role: string };
}

export function HomeNavRail({ lang, active, user }: HomeNavRailProps) {
  return (
    <aside
      className="
        fixed top-0 bottom-0 w-[200px]
        hidden lg:flex flex-col
        bg-surface-1/70 backdrop-blur-xl
        border-l border-r border-border-subtle
        z-20
        rtl:right-0 ltr:left-0
      "
    >
      <div className="px-4 pt-5 pb-4">
        <div className="text-lg font-semibold tracking-tight text-white">
          {homeStrings.appName[lang]}
        </div>
        <div className="text-[11px] text-white/50 mt-0.5">
          {homeStrings.appTagline[lang]}
        </div>
      </div>

      <nav className="flex-1 px-2 py-2 flex flex-col gap-0.5">
        {NAV_ORDER.map(({ key, href, wired }) => {
          const Icon = ICONS[key];
          const isActive = key === active;
          const baseRow = "flex items-center gap-3 h-10 px-3 rounded-lg text-[13px] transition-colors";
          const stateClasses = isActive
            ? "bg-gradient-to-r from-brand-500/20 to-brand-400/5 text-brand-100 ring-1 ring-inset ring-brand-400/30"
            : wired
              ? "text-white/75 hover:bg-white/5 hover:text-white"
              : "text-white/40 hover:bg-white/[0.03]";
          const Inner = (
            <div className={`${baseRow} ${stateClasses}`}>
              <Icon size={16} />
              <span className="flex-1 truncate">{homeStrings.nav[key][lang]}</span>
              {isActive && <span className="w-1 h-5 rounded-full bg-brand-400/80 shadow-[0_0_8px_rgba(64,196,180,0.6)]" />}
            </div>
          );
          return wired
            ? <Link key={key} href={href} aria-current={isActive ? "page" : undefined}>{Inner}</Link>
            : <div key={key} aria-disabled className="cursor-not-allowed">{Inner}</div>;
        })}
      </nav>

      <div className="px-3 py-3 border-t border-border-subtle/60 flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-brand-500/20 ring-1 ring-brand-400/30 grid place-items-center text-[12px] text-brand-100">
          {user.name.split(" ").map(p => p[0]).slice(0, 2).join("")}
        </div>
        <div className="min-w-0">
          <div className="text-[12px] text-white/85 truncate">{user.name}</div>
          <div className="text-[10px] text-white/45 truncate">{user.role}</div>
        </div>
      </div>
    </aside>
  );
}
