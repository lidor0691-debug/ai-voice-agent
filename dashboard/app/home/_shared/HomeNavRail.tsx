"use client";

import Link from "next/link";
import { Activity, Phone, MessageCircle, Users, Sparkles, Bot, Zap, BarChart3, Settings, type LucideIcon } from "lucide-react";
import { homeStrings, NAV_ORDER, type HomeNavKey, type Lang } from "./home-strings";

const ICONS: Record<HomeNavKey, LucideIcon> = {
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

// Phase 1 — only show nav entries that resolve to a real /home/* route.
// Re-add whatsapp/automate/reports/settings to PRIMARY_KEYS/FOOTER_KEYS
// once their pages exist; the disabled-link path was confusing operators.
const PRIMARY_KEYS: HomeNavKey[] = ["watch", "calls", "leads", "insights", "agents"];
const FOOTER_KEYS: HomeNavKey[] = [];

export function HomeNavRail({ lang, active, user }: HomeNavRailProps) {
  const initials = user.name.split(" ").map(p => p[0]).slice(0, 2).join("");

  const renderItem = (key: HomeNavKey) => {
    const entry = NAV_ORDER.find(n => n.key === key);
    if (!entry) return null;
    const Icon = ICONS[key];
    const isActive = key === active;
    const label = homeStrings.nav[key][lang];
    const node = (
      <button
        type="button"
        className={`maya-rail__item ${isActive ? "is-active" : ""}`}
        aria-current={isActive ? "page" : undefined}
        title={label}
        disabled={!entry.wired && !isActive}
      >
        <span className="maya-rail__item-icon" aria-hidden>
          <Icon size={18} strokeWidth={1.7} />
        </span>
        <span className="maya-rail__item-label">{label}</span>
      </button>
    );
    return entry.wired
      ? <Link key={key} href={entry.href}>{node}</Link>
      : <div key={key}>{node}</div>;
  };

  return (
    <aside className="maya-rail hidden lg:flex" aria-label={homeStrings.appName[lang]}>
      <div className="maya-rail__brand">
        <div className="maya-rail__logo" aria-hidden>M</div>
        <div className="maya-rail__brand-text">
          <span className="maya-rail__brand-name">{homeStrings.appName[lang]}</span>
          <span className="maya-rail__brand-sub">{homeStrings.appTagline[lang]}</span>
        </div>
      </div>

      <nav className="maya-rail__nav">
        {PRIMARY_KEYS.map(renderItem)}
        <div className="maya-rail__section">
          {FOOTER_KEYS.map(renderItem)}
        </div>
      </nav>

      <div className="maya-rail__user" title={`${user.name} — ${user.role}`}>
        <div className="maya-rail__avatar" aria-hidden>{initials || "M"}</div>
        <div className="maya-rail__user-text">
          <span className="maya-rail__user-name">{user.name}</span>
          <span className="maya-rail__user-role">{user.role}</span>
        </div>
      </div>
    </aside>
  );
}
