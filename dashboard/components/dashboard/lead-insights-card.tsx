"use client";

import { Brain, ArrowRight } from "lucide-react";
import Link from "next/link";
import RULES from "@/lib/lead-intelligence-rules.json";

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

  // --- Suggested Actions (deterministic rules) ---
  // Each rule checks the clean insight list and fires when a pattern is detected.
  // "weight" = sum of frequency_count for matching rows (0 = no match).
  const totalFreq = (keywords: string[], types?: string[]) =>
    clean
      .filter((r) => {
        const matchType = !types || types.includes(r.insight_type);
        const matchKw = keywords.some((kw) => r.title.includes(kw));
        return matchType && matchKw;
      })
      .reduce((sum, r) => sum + r.frequency_count, 0);

  const SUGGESTION_RULES: { label: string; weight: number }[] = [
    {
      label: "לידים שואלים על מחיר — הוסף/הבהר מחיר מוקדם יותר בשיחה",
      weight: totalFreq(["מחיר", "עולה", "כמה", "תמחור"], ["question", "objection"]),
    },
    {
      label: "לידים מהססים — הוסף מסר ביטחון או טיימינג ל-follow-up",
      weight: totalFreq(["לחשוב", "לא בטוח", "אולי", "נחזור", "מאוחר יותר"], ["objection"]),
    },
    {
      label: "עניין חוזר בבת מצווה — הדגש את החבילה לבת מצווה בהצעה הראשונה",
      weight: totalFreq(["בת מצווה"], ["intent_signal", "interest", "question"]),
    },
    {
      label: "לידים ללא ניסיון — הדגש התאמה למתחילים ותהליך הכניסה",
      weight: totalFreq(["ניסיון", "מתחיל", "לא יודע", "לא מכיר"], ["intent_signal", "question"]),
    },
    {
      label: "שאלות חוזרות על תיאום — שפר את תהליך קביעת הפגישה בשיחה",
      weight: totalFreq(["תאריך", "שעה", "יום", "קבענו", "לתאם"], ["question"]),
    },
  ];

  const suggestions = SUGGESTION_RULES
    .filter((r) => r.weight > 0)
    .sort((a, b) => b.weight - a.weight)
    .slice(0, 3);
  // --- end rules ---

  // --- Suggested Injection Preview (preview only, not used anywhere) ---
  // Each entry fires when its pattern has weight > 0, sentence is shown as-is in the reply preview.
  const INJECTION_RULES = RULES.map((rule) => ({
    sentence: rule.sentence,
    weight: totalFreq(rule.keywords, rule.types),
  }));

  const injectionPreviews = INJECTION_RULES
    .filter((r) => r.weight > 0)
    .sort((a, b) => b.weight - a.weight)
    .slice(0, 2);
  // --- end injection preview ---

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

      {suggestions.length > 0 && (
        <div className="mb-4 rounded-[10px] border border-border p-3" style={{ background: "rgba(167,139,250,0.05)" }}>
          <p className="text-[10px] font-semibold text-brand-400 mb-2">פעולות מוצעות</p>
          <div className="flex flex-col gap-1.5">
            {suggestions.map((s, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="text-brand-400 text-[10px] mt-0.5 flex-shrink-0">→</span>
                <span className="text-gray-300 text-[11px] leading-snug">{s.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {injectionPreviews.length > 0 && (
        <div className="mt-4 rounded-[10px] border border-border p-3" style={{ background: "rgba(59,130,246,0.04)" }}>
          <div className="flex items-center gap-1.5 mb-2">
            <p className="text-[10px] font-semibold text-blue-400">שיפור תשובה מוצע</p>
            <span className="text-[8px] px-1.5 py-0.5 rounded" style={{ color: "#60a5fa", background: "rgba(59,130,246,0.1)" }}>
              preview only
            </span>
          </div>
          <div className="flex flex-col gap-2">
            {injectionPreviews.map((p, i) => (
              <p
                key={i}
                className="text-gray-300 text-[11px] leading-relaxed px-2 py-1.5 rounded-lg"
                style={{ background: "rgba(255,255,255,0.03)", borderRight: "2px solid rgba(59,130,246,0.4)" }}
              >
                "{p.sentence}"
              </p>
            ))}
          </div>
        </div>
      )}

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
