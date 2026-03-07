"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div
      className="flex-1 flex items-center justify-center p-8"
      dir="rtl"
    >
      <div className="text-center max-w-sm">
        <div className="w-14 h-14 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-4">
          <AlertTriangle className="w-7 h-7 text-brand-500" />
        </div>
        <h2 className="text-slate-900 font-semibold text-lg mb-2">
          שגיאה בטעינת הנתונים
        </h2>
        <p className="text-slate-500 text-sm mb-1">
          לא ניתן להתחבר לשרת הנתונים.
        </p>
        <p className="text-slate-400 text-xs mb-6 font-mono bg-slate-50 rounded px-3 py-2 text-right">
          {error.message}
        </p>
        <button
          onClick={reset}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          נסה שוב
        </button>
      </div>
    </div>
  );
}
