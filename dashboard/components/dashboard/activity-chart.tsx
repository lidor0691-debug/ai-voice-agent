"use client";

import { Card, CardHeader, CardContent } from "@/components/ui/card";
import type { Lead } from "@/types/lead";
import { leadsPerDay } from "@/lib/utils";

interface ActivityChartProps {
  leads: Lead[];
}

export function ActivityChart({ leads }: ActivityChartProps) {
  const data = leadsPerDay(leads);
  const maxCount = Math.max(...data.map((d) => d.count), 1);

  return (
    <Card>
      <CardHeader>
        <h2 className="text-slate-800 font-semibold text-sm">
          לידים לפי יום (7 ימים אחרונים)
        </h2>
      </CardHeader>
      <CardContent>
        <div className="flex items-end gap-3 h-32">
          {data.map(({ label, count }) => {
            const heightPct = Math.round((count / maxCount) * 100);
            const shortLabel = new Date(label).toLocaleDateString("he-IL", {
              day: "numeric",
              month: "short",
            });
            return (
              <div
                key={label}
                className="flex-1 flex flex-col items-center gap-1"
              >
                <span className="text-slate-700 text-xs font-semibold tabular-nums">
                  {count}
                </span>
                <div className="w-full flex items-end" style={{ height: 80 }}>
                  <div
                    className="w-full rounded-t-md bg-brand-500 transition-all duration-500"
                    style={{ height: `${heightPct}%` }}
                  />
                </div>
                <span className="text-slate-400 text-xs whitespace-nowrap">
                  {shortLabel}
                </span>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
