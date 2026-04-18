"use client";

import { Trophy } from "lucide-react";

interface WinSignal {
  title: string;
  created_at: string;
}

interface Props {
  signals: WinSignal[] | null;
}

export function WinSignalsCard({ signals }: Props) {
  const recent = signals ?? [];
  const count = recent.length;

  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-3">
        <Trophy className="w-4 h-4" style={{ color: "#fbbf24" }} />
        <div>
          <p className="text-white text-[13px] font-semibold">אותות סגירה</p>
          <p className="text-gray-600 text-[10px] mt-0.5">
            {count > 0 ? `${count} אחרונים` : "אין עדיין"}
          </p>
        </div>
        {count > 0 && (
          <span
            className="mr-auto text-[11px] font-bold px-2 py-0.5 rounded-lg"
            style={{ color: "#fbbf24", background: "rgba(251,191,36,0.12)" }}
          >
            {count}
          </span>
        )}
      </div>

      {count === 0 ? (
        <p className="text-gray-700 text-[11px] text-center py-3">אין אותות סגירה עדיין</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {recent.map((s, i) => (
            <div
              key={i}
              className="flex items-center gap-2 px-2.5 py-2 rounded-[10px] border border-border"
              style={{ background: "rgba(251,191,36,0.03)" }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                style={{ background: "#fbbf24", boxShadow: "0 0 5px #fbbf24" }}
              />
              <span className="text-gray-300 text-[11px] flex-1 truncate">{s.title}</span>
              <span className="text-gray-700 text-[9px] flex-shrink-0">
                {new Date(s.created_at).toLocaleString("he-IL", {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
