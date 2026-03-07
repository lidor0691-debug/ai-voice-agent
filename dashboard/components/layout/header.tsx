import { Bell, Search } from "lucide-react";

interface HeaderProps {
  title: string;
  subtitle?: string;
}

export function Header({ title, subtitle }: HeaderProps) {
  return (
    <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-8 flex-shrink-0">
      <div>
        <h1 className="text-slate-900 font-semibold text-lg leading-none">
          {title}
        </h1>
        {subtitle && (
          <p className="text-slate-500 text-sm mt-0.5">{subtitle}</p>
        )}
      </div>

      <div className="flex items-center gap-3">
        {/* Search */}
        <div className="relative hidden md:block">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="חיפוש..."
            className="pl-9 pr-4 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent w-56"
          />
        </div>

        {/* Notifications */}
        <button className="relative p-2 rounded-lg hover:bg-slate-100 transition-colors">
          <Bell className="w-5 h-5 text-slate-500" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-brand-500 rounded-full" />
        </button>

        {/* Live indicator */}
        <div className="flex items-center gap-2 px-3 py-1.5 bg-green-50 border border-green-200 rounded-full">
          <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span className="text-green-700 text-xs font-medium">פעיל</span>
        </div>
      </div>
    </header>
  );
}
