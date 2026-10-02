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
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary text-lg font-semibold text-primary-foreground">
            {initials(user.full_name)}
          </div>
          <div>
            <p className="font-semibold">{user.full_name}</p>
            <Badge variant="outline" className="mt-1">
              {ROLE_LABEL[user.role]}
            </Badge>
          </div>
        </div>

        <div className="flex flex-col gap-3 pt-4 text-sm">
          <div className="flex items-center gap-2.5">
            <Mail className="h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">Email</span>
            <span className="ml-auto font-medium">{user.email}</span>
          </div>
          <div className="flex items-center gap-2.5">
            <ShieldCheck className="h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">Trạng thái</span>
            <Badge variant={user.is_active ? "success" : "destructive"} className="ml-auto">
              {user.is_active ? "Đang hoạt động" : "Đã khoá"}
            </Badge>
          </div>
          <div className="flex items-center gap-2.5">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">Ngày tạo tài khoản</span>
            <span className="ml-auto font-medium">{formatDate(user.created_at)}</span>
          </div>
          <div className="flex items-center gap-2.5">
            <CircleUser className="h-4 w-4 text-muted-foreground" />
            <span className="text-muted-foreground">Mã người dùng</span>
            <span className="ml-auto truncate font-mono text-xs text-muted-foreground">{user.id}</span>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
