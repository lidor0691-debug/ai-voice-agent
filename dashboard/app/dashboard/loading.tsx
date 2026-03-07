import { StatCardSkeleton, TableSkeleton } from "@/components/ui/skeleton";

export default function DashboardLoading() {
  return (
    <div className="flex-1 overflow-y-auto p-8 space-y-6" dir="rtl">
      {/* KPI skeletons */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <StatCardSkeleton key={i} />
        ))}
      </div>
      {/* Table skeleton */}
      <TableSkeleton rows={5} />
    </div>
  );
}
