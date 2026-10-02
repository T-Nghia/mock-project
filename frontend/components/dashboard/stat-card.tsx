import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const COLOR_VARIANTS = [
  "bg-blue-50 text-blue-600",
  "bg-violet-50 text-violet-600",
  "bg-emerald-50 text-emerald-600",
  "bg-amber-50 text-amber-600",
];

export function StatCard({
  label,
  value,
  icon: Icon,
  description,
  colorIndex = 0,
  className,
}: {
  label: string;
  value: number | string;
  icon: React.ElementType;
  description?: string;
  colorIndex?: number;
  className?: string;
}) {
  const colorClass = COLOR_VARIANTS[colorIndex % COLOR_VARIANTS.length];
  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-1">{label}</p>
            <p className="text-3xl font-bold tracking-tight leading-none">{value}</p>
            {description && (
              <p className="mt-1.5 text-xs text-muted-foreground">{description}</p>
            )}
          </div>
          <div className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ml-4", colorClass)}>
            <Icon className="h-5 w-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
