import { Badge } from "@/components/ui/badge";
import type { ProcessingStatus } from "@/lib/types";

const CONFIG: Record<ProcessingStatus, { label: string; variant: "success" | "warning" | "destructive" | "secondary" }> = {
  pending: { label: "Chờ xử lý", variant: "secondary" },
  processing: { label: "Đang xử lý", variant: "warning" },
  done: { label: "Hoàn tất", variant: "success" },
  failed: { label: "Lỗi xử lý", variant: "destructive" },
};

export function StatusBadge({ status }: { status: ProcessingStatus | string }) {
  const cfg = CONFIG[status as ProcessingStatus] ?? { label: status, variant: "secondary" as const };
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}
