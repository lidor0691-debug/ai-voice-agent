"use client";

import { AlertTriangle, Lightbulb, Trophy, Sparkles, type LucideIcon } from "lucide-react";
import type { Alert, Insight, Win, Pattern } from "../watch-mock";
import { watchStrings } from "../watch-strings";
import type { Lang } from "../../_shared/home-strings";

interface ActivityRailProps {
  alerts: Alert[];
  insights: Insight[];
  wins: Win[];
  patterns: Pattern[];
  lang: Lang;
}

export function ActivityRail({ alerts, insights, wins, patterns, lang }: ActivityRailProps) {
  const t = watchStrings.rails;
  return (
    <aside className="flex flex-col gap-4">
      <Section icon={AlertTriangle} title={t.alerts[lang]} tone="amber">
        {alerts.map(a => (
          <div key={a.id} className="card bg-surface-2/60 border border-border-subtle rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              <SeverityDot sev={a.severity} />
              <span className="text-[12px] text-white/85">{a.who}</span>
              <span className="ms-auto text-[10px] text-white/40">{a.ago}</span>
            </div>
            <div className="text-[12px] text-white/65 leading-snug">{a.body}</div>
          </div>
        ))}
      </Section>

      <Section icon={Lightbulb} title={t.insights[lang]} tone="brand">
        {insights.map((i, idx) => (
          <div key={idx} className="card bg-surface-2/60 border border-border-subtle rounded-lg p-3">
            <div className="text-[12px] text-white/85 leading-snug mb-1">{i.head}</div>
            <div className="text-[11px] text-white/55 leading-snug mb-2">{i.body}</div>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1 rounded-full bg-white/10 overflow-hidden">
                <div className="h-full bg-brand-400" style={{ width: `${Math.round(i.conf * 100)}%` }} />
              </div>
              <span className="text-[10px] text-brand-200">{Math.round(i.conf * 100)}%</span>
            </div>
          </div>
        ))}
      </Section>

      <Section icon={Trophy} title={t.wins[lang]} tone="emerald">
        <div className="card bg-surface-2/60 border border-border-subtle rounded-lg divide-y divide-white/5">
          {wins.map((w, i) => (
            <div key={i} className="flex items-center justify-between px-3 py-2.5">
              <div className="min-w-0">
                <div className="text-[12px] text-white/85 truncate">{w.name}</div>
                <div className="text-[10px] text-white/50 truncate">{w.desc}</div>
              </div>
              <div className="text-[12px] text-emerald-300 font-medium">{w.value}</div>
            </div>
          ))}
        </div>
      </Section>

      <Section icon={Sparkles} title={t.patterns[lang]} tone="brand">
        {patterns.map((p, i) => (
          <div key={i} className="card bg-surface-2/60 border border-border-subtle rounded-lg p-3">
            <div className="text-[12px] text-white/85 leading-snug mb-1">{p.head}</div>
            <div className="text-[11px] text-white/55 leading-snug">{p.body}</div>
          </div>
        ))}
      </Section>
    </aside>
  );
}

function Section({
  icon: Icon, title, tone, children,
}: {
  icon: LucideIcon;
  title: string;
  tone: "amber" | "brand" | "emerald";
  children: React.ReactNode;
}) {
  const toneClass = tone === "amber" ? "text-amber-300" : tone === "emerald" ? "text-emerald-300" : "text-brand-200";
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 px-1">
        <Icon size={12} className={toneClass} />
        <span className="maya-section-label">{title}</span>
      </div>
      <div className="flex flex-col gap-2">{children}</div>
    </div>
  );
}

function SeverityDot({ sev }: { sev: "high" | "med" | "low" }) {
  const c = sev === "high" ? "bg-rose-400" : sev === "med" ? "bg-amber-300" : "bg-white/40";
  return <span className={`w-2 h-2 rounded-full ${c}`} />;
}
