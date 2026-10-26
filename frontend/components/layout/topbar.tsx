"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight, LogOut, Menu, Search, User as UserIcon } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { initials } from "@/lib/utils";
import type { UserRole } from "@/lib/types";
import { ProfileDialog } from "./profile-dialog";

const ROLE_LABEL: Record<UserRole, string> = {
  admin: "Quản trị viên",
  teacher: "Giáo viên",
  student: "Học sinh",
};

interface TopbarProps {
  title: string;
  mobileOpen: boolean;
  onOpenNavigation: () => void;
}

export function Topbar({ title, mobileOpen, onOpenNavigation }: TopbarProps) {
  const { user, logout } = useAuth();
  const [profileOpen, setProfileOpen] = useState(false);
  if (!user) return null;

  return (
    <header className="relative z-20 flex h-16 shrink-0 items-center justify-between gap-2 border-b border-border bg-card px-3 sm:gap-4 sm:px-6 lg:px-8">
      <div className="flex min-w-0 items-center gap-2 sm:gap-3">
        <Button variant="ghost" size="icon" className="h-11 w-11 shrink-0 lg:hidden" onClick={onOpenNavigation} aria-label="Mở thanh điều hướng" aria-haspopup="dialog" aria-expanded={mobileOpen} aria-controls={mobileOpen ? "mobile-navigation" : undefined}>
          <Menu aria-hidden="true" className="h-5 w-5" />
        </Button>
        <span className="hidden shrink-0 text-sm text-muted-foreground xl:inline">Không gian học tập</span>
        <ChevronRight aria-hidden="true" className="hidden h-3.5 w-3.5 shrink-0 text-muted-foreground/60 xl:block" />
        <h1 className="truncate text-sm font-semibold tracking-tight sm:text-[15px]" title={title}>{title}</h1>
      </div>

      <div className="flex shrink-0 items-center gap-1.5 sm:gap-4">
        <Link href="/search" aria-label="Tìm kiếm tài liệu" className="flex h-11 w-11 items-center justify-center gap-2.5 rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground sm:h-9 sm:w-44 sm:justify-start sm:border sm:border-border sm:bg-background sm:px-3 lg:w-52">
          <Search aria-hidden="true" className="h-4 w-4 shrink-0" />
          <span className="hidden text-sm sm:inline">Tìm tài liệu…</span>
        </Link>
        <span aria-hidden="true" className="hidden h-6 w-px bg-border sm:block" />
        <DropdownMenu>
          <DropdownMenuTrigger aria-label="Mở menu tài khoản" className="flex min-h-11 items-center gap-2 rounded-md p-1.5 transition-colors hover:bg-accent sm:gap-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary ring-1 ring-inset ring-primary/10">
              {initials(user.full_name)}
            </span>
            <span className="hidden max-w-32 text-left lg:block">
              <span className="block truncate text-xs font-semibold leading-5">{user.full_name}</span>
              <span className="block text-[11px] leading-4 text-muted-foreground">{ROLE_LABEL[user.role]}</span>
            </span>
            <ChevronDown aria-hidden="true" className="hidden h-3.5 w-3.5 text-muted-foreground sm:block" />
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-64">
            <div role="presentation" className="px-3 py-2.5">
              <p className="break-words text-sm font-semibold">{user.full_name}</p>
              <p className="mt-0.5 break-all text-xs text-muted-foreground">{user.email}</p>
              <Badge variant="secondary" className="mt-2">{ROLE_LABEL[user.role]}</Badge>
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => setProfileOpen(true)}>
              <UserIcon aria-hidden="true" className="h-4 w-4" /> Hồ sơ của tôi
            </DropdownMenuItem>
            <DropdownMenuItem onClick={logout} className="text-destructive hover:bg-destructive/5 hover:text-destructive focus:bg-destructive/5 focus:text-destructive">
              <LogOut aria-hidden="true" className="h-4 w-4" /> Đăng xuất
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <ProfileDialog open={profileOpen} onOpenChange={setProfileOpen} />
    </header>
  );
}
