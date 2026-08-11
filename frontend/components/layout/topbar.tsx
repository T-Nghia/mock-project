"use client";

import { useState } from "react";
import { LogOut, User as UserIcon } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { initials } from "@/lib/utils";
import type { UserRole } from "@/lib/types";
import { ProfileDialog } from "./profile-dialog";

const ROLE_LABEL: Record<UserRole, string> = {
  admin: "Quản trị viên",
  teacher: "Giáo viên",
  student: "Học sinh",
};

export function Topbar({ title }: { title: string }) {
  const { user, logout } = useAuth();
  const [profileOpen, setProfileOpen] = useState(false);
  if (!user) return null;

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-card/60 px-5 backdrop-blur">
      <h1 className="text-base font-semibold">{title}</h1>
      <div className="flex items-center gap-3">
        <Badge variant="outline" className="hidden sm:inline-flex">
          {ROLE_LABEL[user.role]}
        </Badge>
        <DropdownMenu>
          <DropdownMenuTrigger>
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
              {initials(user.full_name)}
            </div>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <div className="px-2.5 py-1.5">
              <p className="text-sm font-medium">{user.full_name}</p>
              <p className="text-xs text-muted-foreground">{user.email}</p>
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => setProfileOpen(true)}>
              <UserIcon className="h-4 w-4" /> Hồ sơ của tôi
            </DropdownMenuItem>
            <DropdownMenuItem onClick={logout} className="text-destructive">
              <LogOut className="h-4 w-4" /> Đăng xuất
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <ProfileDialog open={profileOpen} onOpenChange={setProfileOpen} />
    </header>
  );
}
