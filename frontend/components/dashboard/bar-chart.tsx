import { cn } from "@/lib/utils";

interface BarChartProps {
  data: { label: string; value: number }[];
  className?: string;
  barClassName?: string;
}

export function BarChart({ data, className, barClassName }: BarChartProps) {
  const max = Math.max(1, ...data.map((d) => d.value));

  if (data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-10 text-center">
        <div className="mb-2 text-3xl">📊</div>
        <p className="text-sm text-muted-foreground">Chưa có dữ liệu.</p>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {data.map((d, i) => (
        <div key={d.label} className="group flex items-center gap-3">
          <span className="w-32 shrink-0 truncate text-xs text-muted-foreground transition-colors group-hover:text-foreground" title={d.label}>
            {d.label}
          </span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-700 ease-out",
                barClassName ?? (i % 2 === 0 ? "gradient-brand" : "bg-primary/60")
              )}
              style={{
                width: `${(d.value / max) * 100}%`,
                animationDelay: `${i * 80}ms`,
              }}
            />
          </div>
          <span className="w-10 shrink-0 text-right text-xs font-semibold tabular-nums text-foreground">
            {d.value}
          </span>
        </div>
      ))}
    </div>
  );
}
