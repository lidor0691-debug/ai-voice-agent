import { cn } from "@/lib/utils";
import type { LeadStatus } from "@/types/lead";

type BadgeVariant =
  | "default"
  | "success"
  | "warning"
  | "danger"
  | "brand"
  | "info"
  | "muted";

const VARIANT_CLASSES: Record<BadgeVariant, string> = {
  default: "bg-slate-100 text-slate-700",
  success: "bg-green-100 text-green-700",
  warning: "bg-amber-100 text-amber-700",
  danger: "bg-red-100 text-red-700",
  brand: "bg-brand-100 text-brand-700",
  info: "bg-blue-100 text-blue-700",
  muted: "bg-slate-100 text-slate-400",
};

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  className?: string;
}

export function Badge({ children, variant = "default", className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium whitespace-nowrap",
        VARIANT_CLASSES[variant],
        className
      )}
    >
      {children}
    </span>
  );
}

/** Maps any status string to a colour variant. Unknown statuses get "default". */
export function StatusBadge({ status }: { status: LeadStatus }) {
  const map: Record<string, BadgeVariant> = {
    "new": "brand",
    "ליד חדש": "brand",
    "בטיפול": "warning",
    "SMS נשלח": "success",
    "תור נקבע": "info",
  };
  const label = status === "new" ? "ליד חדש" : status;
  return <Badge variant={map[status] ?? "default"}>{label}</Badge>;
}

export function BoolBadge({ value, labelTrue, labelFalse }: {
  value: boolean;
  labelTrue?: string;
  labelFalse?: string;
}) {
  return value ? (
    <Badge variant="success">{labelTrue ?? "✓"}</Badge>
  ) : (
    <Badge variant="muted">{labelFalse ?? "—"}</Badge>
  );
}
