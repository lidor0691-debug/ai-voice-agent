"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLanguage } from "@/context/language-context";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { lang } = useLanguage();

  const tabs = [
    { href: "/admin", label: "Clients" },
    { href: "/admin/client-setup", label: lang === "en" ? "Client Setup" : "הקמת לקוח" },
    { href: "/admin/users", label: "Users" },
    { href: "/admin/audit", label: "Audit Log" },
    { href: "/admin/briefings", label: "Briefings" },
  ];

  return (
    <div className="min-h-screen bg-surface-0 text-white">
      <div className="border-b border-border px-8 py-4 flex items-center gap-3">
        <span className="text-brand-400 text-xs font-mono bg-brand-600/20 px-2 py-0.5 rounded">
          ADMIN
        </span>
        <span className="text-white font-semibold text-sm">Maya AI — Admin Panel</span>
      </div>
      <div className="px-8 border-b border-border">
        <div className="flex gap-1">
          {tabs.map((tab) => {
            const active = pathname === tab.href;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
                  active
                    ? "text-white border-brand-600"
                    : "text-gray-500 border-transparent hover:text-gray-300"
                }`}
              >
                {tab.label}
              </Link>
            );
          })}
        </div>
      </div>
      <div className="p-8">{children}</div>
    </div>
  );
}
