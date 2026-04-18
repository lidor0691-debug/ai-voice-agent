"use client";

import { Brain, ArrowRight } from "lucide-react";
import Link from "next/link";

interface Insight {
  insight_type: string;
  title: string;
  frequency_count: number;
  created_at: string;
}

interface Props {
  insights: Insight[] | null;
}

const TYPE_COLORS: Record<string, { color: string; bg: string }> = {
  objection:      { color: "#ef4444", bg: "rgba(239,68,68,0.1)" },
  interest:       { color: "#10b981", bg: "rgba(16,185,129,0.1)" },
  question:       { color: "#60a5fa", bg: "rgba(59,130,246,0.1)" },
  pain_point:     { color: "#f59e0b", bg: "rgba(245,158,11,0.1)" },
  buying_signal:  { color: "#a78bfa", bg: "rgba(139,92,246,0.1)" },
};

function typeStyle(type: string) {
  return TYPE_COLORS[type] ?? { color: "#94a3b8", bg: "rgba(148,163,184,0.1)" };
}

export function LeadInsightsCard({ insights }: Props) {
  if (!insights || insights.length === 0) {
    return (
      <div className="card p-4">
        <div className="flex items-center gap-2 mb-3">
          <Brain className="w-4 h-4 text-brand-400" />
          <p className="text-white text-[13px] font-semibold">Lead Intelligence</p>
        </div>
        <p className="text-gray-700 text-[11px] text-center py-3">אין תובנות עדיין</p>
      </div>
    );
  }

  // Filter bad rows: empty title, placeholder "insight", or corrupted (only ?, spaces, punctuation)
  const clean = insights.filter((row) => {
    const t = row.title?.trim();
    if (!t) return false;
    if (t.toLowerCase() === "insight") return false;
    if (/^[?\s\p{P}]+$/u.test(t)) return false;
    return true;
  });

  // Group by insight_type
  const grouped = clean.reduce<Record<string, Insight[]>>((acc, row) => {
    (acc[row.insight_type] ??= []).push(row);
    return acc;
  }, {});

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Brain className="w-4 h-4 text-brand-400" />
          <div>
            <p className="text-white text-[13px] font-semibold">Lead Intelligence</p>
            <p className="text-gray-600 text-[10px] mt-0.5">
              {insights.length} תובנות אחרונות
            </p>
          </div>
        </div>
        <Link
          href="/dashboard/leads"
          className="text-brand-400 text-[10px] flex items-center gap-1 hover:text-brand-300 transition-colors"
        >
          לידים <ArrowRight className="w-3 h-3" />
        </Link>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
        {Object.entries(grouped).map(([type, rows]) => {
          const { color, bg } = typeStyle(type);
          return (
            <div
              key={type}
              className="rounded-[10px] border border-border p-3"
              style={{ background: "rgba(255,255,255,0.02)" }}
            >
              <div className="flex items-center gap-1.5 mb-2">
                <span
                  className="text-[9px] font-semibold px-1.5 py-0.5 rounded capitalize"
                  style={{ color, background: bg }}
                >
                  {type.replace(/_/g, " ")}
                </span>
                <span className="text-gray-600 text-[9px]">
                  {rows.length} פריטים
                </span>
              </div>
              <div className="flex flex-col gap-1">
                {rows.map((row, i) => (
                  <div key={i} className="flex items-center justify-between gap-2">
                    <span className="text-gray-400 text-[11px] truncate flex-1">
                      {row.title}
                    </span>
                    <span
                      className="text-[9px] font-semibold px-1.5 py-0.5 rounded flex-shrink-0"
                      style={{ color, background: bg }}
                    >
                      ×{row.frequency_count}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
