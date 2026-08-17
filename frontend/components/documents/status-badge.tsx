import { cn } from "@/lib/utils";
import type { ProcessingStatus } from "@/lib/types";

const CONFIG: Record<
  ProcessingStatus,
  { label: string; dot: string; text: string; bg: string }
> = {
  pending:    { label: "Chờ xử lý", dot: "bg-slate-400",  text: "text-slate-700", bg: "bg-slate-100" },
  processing: { label: "Đang xử lý", dot: "bg-amber-400 animate-pulse", text: "text-amber-700", bg: "bg-amber-50" },
  done:       { label: "Hoàn tất",   dot: "bg-emerald-500", text: "text-emerald-700", bg: "bg-emerald-50" },
  failed:     { label: "Lỗi xử lý", dot: "bg-red-500",    text: "text-red-700",    bg: "bg-red-50" },
};

export function StatusBadge({ status }: { status: ProcessingStatus | string }) {
  const cfg = CONFIG[status as ProcessingStatus] ?? {
    label: status,
    dot: "bg-slate-400",
    text: "text-slate-700",
    bg: "bg-slate-100",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
        cfg.bg,
        cfg.text
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", cfg.dot)} />
      {cfg.label}
    </span>
  );
}
