export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-surface-0 text-white">
      <div className="border-b border-border px-8 py-4 flex items-center gap-3">
        <span className="text-brand-400 text-xs font-mono bg-brand-600/20 px-2 py-0.5 rounded">
          ADMIN
        </span>
        <span className="text-white font-semibold text-sm">Maya AI — Admin Panel</span>
      </div>
      <div className="p-8">{children}</div>
    </div>
  );
}
