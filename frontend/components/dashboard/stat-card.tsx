import type { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

interface StatCardProps {
  label: string;
  value: number;
  description: string;
  icon: LucideIcon;
}

export function StatCard({ label, value, description, icon: Icon }: StatCardProps) {
  return (
    <Card role="group" aria-label={label} className="min-h-[156px]">
      <CardContent className="p-5">
        <div className="mb-3 flex items-center justify-between gap-3">
          <p className="text-sm font-medium text-muted-foreground">{label}</p>
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/5 text-primary">
            <Icon aria-hidden="true" className="h-[18px] w-[18px]" strokeWidth={1.75} />
          </span>
        </div>
        <p className="break-words text-3xl font-semibold tracking-tight tabular-nums">{value.toLocaleString("vi-VN")}</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  );
}
