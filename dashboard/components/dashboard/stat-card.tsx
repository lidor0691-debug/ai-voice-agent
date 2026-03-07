import { type LucideIcon, TrendingUp } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  trend?: number;
  icon: LucideIcon;
  iconColor?: string;
  iconBg?: string;
}

export function StatCard({
  title,
  value,
  subtitle,
  trend,
  icon: Icon,
  iconColor = "text-brand-600",
  iconBg = "bg-brand-50",
}: StatCardProps) {
  return (
    <Card className="p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <p className="text-slate-500 text-sm font-medium truncate">{title}</p>
          <p className="text-slate-900 text-3xl font-bold mt-1 tabular-nums">
            {value}
          </p>
          {subtitle && (
            <p className="text-slate-400 text-xs mt-1">{subtitle}</p>
          )}
          {trend !== undefined && (
            <div
              className={cn(
                "flex items-center gap-1 mt-2 text-xs font-medium",
                trend >= 0 ? "text-green-600" : "text-red-500"
              )}
            >
              <TrendingUp
                className={cn("w-3 h-3", trend < 0 && "rotate-180")}
              />
              <span>
                {trend >= 0 ? "+" : ""}
                {trend}% השבוע
              </span>
            </div>
          )}
        </div>
        <div
          className={cn(
            "w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0",
            iconBg
          )}
        >
          <Icon className={cn("w-6 h-6", iconColor)} />
        </div>
      </div>
    </Card>
  );
}
