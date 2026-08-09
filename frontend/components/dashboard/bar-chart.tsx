import { cn } from "@/lib/utils";

interface BarChartProps {
  data: { label: string; value: number }[];
  className?: string;
  barClassName?: string;
}

export function BarChart({ data, className, barClassName }: BarChartProps) {
  const max = Math.max(1, ...data.map((d) => d.value));

  if (data.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">Chưa có dữ liệu.</p>;
  }

  return (
    <div className={cn("flex flex-col gap-2.5", className)}>
      {data.map((d) => (
        <div key={d.label} className="flex items-center gap-3">
          <span className="w-28 shrink-0 truncate text-xs text-muted-foreground" title={d.label}>
            {d.label}
          </span>
          <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-muted">
            <div
              className={cn("h-full rounded-full bg-primary transition-all", barClassName)}
              style={{ width: `${(d.value / max) * 100}%` }}
            />
          </div>
          <span className="w-8 shrink-0 text-right text-xs font-medium">{d.value}</span>
        </div>
      ))}
    </div>
  );
}
