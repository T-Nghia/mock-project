"use client";

import { Mail, ShieldCheck, Calendar, CircleUser } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { initials, formatDate } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";
import type { UserRole } from "@/lib/types";

const ROLE_LABEL: Record<UserRole, string> = {
  admin: "Quản trị viên",
  teacher: "Giáo viên",
  student: "Học sinh",
};

export function ProfileDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { user } = useAuth();
  if (!user) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>Hồ sơ của tôi</DialogTitle>
        </DialogHeader>

        <div className="flex items-center gap-3 border-b border-border pb-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-primary text-lg font-semibold text-primary-foreground">
            {initials(user.full_name)}
          </div>
          <div className="min-w-0">
            <p className="break-words font-semibold">{user.full_name}</p>
            <Badge variant="outline" className="mt-1">
              {ROLE_LABEL[user.role]}
            </Badge>
          </div>
        </div>

        <div className="flex flex-col gap-3 pt-4 text-sm">
          <div className="grid grid-cols-[1rem_minmax(0,1fr)] items-start gap-x-3 gap-y-1 sm:grid-cols-[1rem_auto_minmax(0,1fr)]">
            <Mail aria-hidden="true" className="mt-0.5 h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">Email</span>
            <span className="col-start-2 min-w-0 break-all font-medium sm:col-start-3 sm:text-right">{user.email}</span>
          </div>
          <div className="grid grid-cols-[1rem_minmax(0,1fr)] items-start gap-x-3 gap-y-1 sm:grid-cols-[1rem_auto_minmax(0,1fr)]">
            <ShieldCheck aria-hidden="true" className="mt-0.5 h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">Trạng thái</span>
            <Badge variant={user.is_active ? "success" : "destructive"} className="col-start-2 w-fit sm:col-start-3 sm:justify-self-end">
              {user.is_active ? "Đang hoạt động" : "Đã khoá"}
            </Badge>
          </div>
          <div className="grid grid-cols-[1rem_minmax(0,1fr)] items-start gap-x-3 gap-y-1 sm:grid-cols-[1rem_auto_minmax(0,1fr)]">
            <Calendar aria-hidden="true" className="mt-0.5 h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">Ngày tạo tài khoản</span>
            <span className="col-start-2 font-medium sm:col-start-3 sm:text-right">{formatDate(user.created_at)}</span>
          </div>
          <div className="grid grid-cols-[1rem_minmax(0,1fr)] items-start gap-x-3 gap-y-1 sm:grid-cols-[1rem_auto_minmax(0,1fr)]">
            <CircleUser aria-hidden="true" className="mt-0.5 h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">Mã người dùng</span>
            <span className="col-start-2 min-w-0 break-all font-mono text-xs text-muted-foreground sm:col-start-3 sm:text-right">{user.id}</span>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
