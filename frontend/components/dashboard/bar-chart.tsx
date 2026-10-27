import { ChartNoAxesColumn } from "lucide-react";
import { cn } from "@/lib/utils";

interface BarChartProps {
  data: { label: string; value: number; description?: string }[];
  label: string;
  unit?: string;
  orientation?: "horizontal" | "vertical";
  emptyMessage?: string;
  className?: string;
}

export function BarChart({ data, label, unit = "tài liệu", orientation = "horizontal", emptyMessage = "Chưa có dữ liệu thống kê.", className }: BarChartProps) {
  const max = Math.max(1, ...data.map((point) => point.value));
  const hasValues = data.some((point) => point.value > 0);

  if (!hasValues) return (
    <div role="status" className={cn("flex min-h-56 flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-background/50 px-5 py-8 text-center", className)}>
      <ChartNoAxesColumn aria-hidden="true" className="h-7 w-7 text-muted-foreground" strokeWidth={1.5} />
      <p className="max-w-xs text-sm leading-6 text-muted-foreground">{emptyMessage}</p>
    </div>
  );

  return (
    <figure aria-label={label} className={cn("min-w-0", className)}>
      <figcaption className="sr-only">{label}. Đơn vị: {unit}.</figcaption>
      {orientation === "vertical" ? (
        <div className="relative pt-2">
          <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-12 flex h-[168px] flex-col justify-between">
            {[0, 1, 2, 3].map((line) => <div key={line} className="border-t border-dashed border-border" />)}
          </div>
          <ul className="relative flex items-end gap-1 sm:gap-2">
            {data.map((point, index) => (
              <li key={`${point.label}-${index}`} className="min-w-0 flex-1 text-center" title={`${point.description ?? point.label}: ${point.value.toLocaleString("vi-VN")} ${unit}`}>
                <div className="flex h-52 flex-col justify-end gap-2">
                  <span className="break-words text-[10px] font-medium tabular-nums text-foreground sm:text-xs">{point.value.toLocaleString("vi-VN")}</span>
                  <div aria-hidden="true" className="mx-auto w-3/5 max-w-11 rounded-t-md bg-primary/85" style={{ height: `${(point.value / max) * 168}px` }} />
                </div>
                <span className="mt-3 block text-[10px] tabular-nums text-muted-foreground sm:text-xs" aria-hidden="true">{point.label}</span>
                <span className="sr-only">{unit}, {point.description ?? point.label}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <ul className="space-y-5">
          {data.map((point, index) => (
            <li key={`${point.label}-${index}`}>
              <div className="mb-2 flex items-start justify-between gap-3 text-sm">
                <span className="min-w-0 break-words leading-5 text-muted-foreground">{point.label}</span>
                <span className="shrink-0 font-medium tabular-nums">{point.value.toLocaleString("vi-VN")}<span className="sr-only"> {unit}</span></span>
              </div>
              <div aria-hidden="true" className="h-2 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-primary/80" style={{ width: `${(point.value / max) * 100}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </figure>
  );
}
