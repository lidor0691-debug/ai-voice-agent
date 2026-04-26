"use client";

import { Search, LogOut, Menu } from "lucide-react";
import { useLanguage } from "@/context/language-context";
import { useRouter } from "next/navigation";
import { createSupabaseBrowserClient } from "@/lib/supabase-browser";
import { useSidebar } from "@/components/layout/dashboard-shell";

interface Props {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export function Header({ title, subtitle, action }: Props) {
  const { lang, setLang, t } = useLanguage();
  const router = useRouter();
  const supabase = createSupabaseBrowserClient();
  const { toggle } = useSidebar();

  async function handleLogout() {
    await supabase.auth.signOut();
    router.push("/login");
  }

  return (
    <div className="h-14 border-b border-border flex items-center justify-between px-3 md:px-6 flex-shrink-0 bg-surface-1">
      {/* Mobile hamburger */}
      <button
        onClick={toggle}
        className="md:hidden flex items-center justify-center w-10 h-10 -ms-1 rounded-lg text-gray-400 hover:text-white hover:bg-surface-3 transition-colors"
        aria-label="Toggle menu"
      >
        <Menu className="w-5 h-5" />
      </button>

      {/* Page info */}
      <div>
        <h1 className="text-white font-semibold text-sm tracking-tight">{title}</h1>
        {subtitle && <p className="text-gray-600 text-[11px] mt-0.5">{subtitle}</p>}
      </div>

      <div className="flex items-center gap-2.5">
        {/* Search */}
        <div className="relative hidden md:block">
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

        {/* Logout */}
        <button
          onClick={handleLogout}
          className="hidden md:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium text-gray-500 hover:text-red-400 hover:bg-red-500/10 border border-transparent hover:border-red-500/20 transition-colors"
        >
          <LogOut className="w-3.5 h-3.5" />
          {t.logout ?? "Logout"}
        </button>
      </div>
    </div>
  );
}
