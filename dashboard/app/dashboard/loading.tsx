export default function DashboardLoading() {
  return (
    <div className="flex-1 overflow-y-auto p-8">
      <div className="animate-pulse space-y-6">
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-surface-2 border border-border rounded-xl h-28" />
          ))}
        </div>
        <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
          <div className="xl:col-span-3 bg-surface-2 border border-border rounded-xl h-96" />
          <div className="xl:col-span-2 space-y-4">
            <div className="bg-surface-2 border border-border rounded-xl h-44" />
            <div className="bg-surface-2 border border-border rounded-xl h-44" />
          </div>
        </div>
      </div>
    </div>
  );
}
