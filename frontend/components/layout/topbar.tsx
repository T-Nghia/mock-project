"use client";

import { useState } from "react";
import { LogOut, User as UserIcon, Bell } from "lucide-react";
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

const ROLE_COLOR: Record<UserRole, string> = {
  admin:   "bg-purple-100 text-purple-700 border-purple-200",
  teacher: "bg-sky-100 text-sky-700 border-sky-200",
  student: "bg-emerald-100 text-emerald-700 border-emerald-200",
};

export function Topbar({ title }: { title: string }) {
  const { user, logout } = useAuth();
  const [profileOpen, setProfileOpen] = useState(false);
  if (!user) return null;

  return (
    <header className="flex h-14 items-center justify-between border-b border-border/60 bg-card/80 px-5 backdrop-blur-sm">
      <h1 className="text-sm font-semibold tracking-tight text-foreground">{title}</h1>

      <div className="flex items-center gap-2.5">
        {/* Notification bell (decorative) */}
        <button className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors">
          <Bell className="h-4 w-4" />
        </button>

        {/* Role badge */}
        <span
          className={`hidden sm:inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${ROLE_COLOR[user.role]}`}
        >
          {ROLE_LABEL[user.role]}
        </span>

        {/* User menu */}
        <DropdownMenu>
          <DropdownMenuTrigger>
            <button className="flex h-8 w-8 items-center justify-center rounded-full gradient-brand text-xs font-bold text-white shadow-sm ring-2 ring-primary/20 transition-all hover:ring-4 focus:outline-none">
              {initials(user.full_name)}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            <div className="px-2.5 py-2">
              <p className="text-sm font-semibold truncate">{user.full_name}</p>
              <p className="text-xs text-muted-foreground truncate">{user.email}</p>
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => setProfileOpen(true)}>
              <UserIcon className="h-4 w-4" /> Hồ sơ của tôi
            </DropdownMenuItem>
            <DropdownMenuItem onClick={logout} className="text-destructive focus:text-destructive">
              <LogOut className="h-4 w-4" /> Đăng xuất
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <ProfileDialog open={profileOpen} onOpenChange={setProfileOpen} />
    </header>
  );
}
