"use client";

import { Search } from "lucide-react";
import { useLanguage } from "@/context/language-context";

interface Props {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export function Header({ title, subtitle, action }: Props) {
  const { lang, setLang, t } = useLanguage();

  return (
    <div className="h-14 border-b border-border flex items-center justify-between px-6 flex-shrink-0 bg-surface-1">
      {/* Page info */}
      <div>
        <h1 className="text-white font-semibold text-sm tracking-tight">{title}</h1>
        {subtitle && <p className="text-gray-600 text-[11px] mt-0.5">{subtitle}</p>}
      </div>

      <div className="flex items-center gap-2.5">
        {/* Search */}
        <div className="relative">
          <Search className="absolute top-1/2 -translate-y-1/2 start-3 w-3.5 h-3.5 text-gray-600" />
          <input
            placeholder={t.search_placeholder}
            className="bg-surface-2 border border-border rounded-lg ps-9 pe-3 py-1.5 text-xs text-white placeholder-gray-600
              focus:outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500 w-44 transition-colors"
          />
        </div>

        {/* Live chip */}
        <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <span className="live-dot" />
          {t.status_active}
        </span>

        {/* Language toggle */}
        <div className="flex items-center gap-0.5 bg-surface-2 border border-border rounded-lg p-0.5">
          {(["he", "en"] as const).map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors ${
                lang === l
                  ? "bg-gradient-to-br from-brand-500 to-indigo-500 text-white shadow-glow-sm"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              {l === "he" ? t.lang_he : t.lang_en}
            </button>
          ))}
        </div>

        {/* Optional page CTA */}
        {action}
      </div>
    </div>
  );
}
