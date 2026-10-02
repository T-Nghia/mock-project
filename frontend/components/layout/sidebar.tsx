"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FolderTree,
  Search,
  UploadCloud,
  Users,
  FileText,
  BookOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { UserRole } from "@/lib/types";

interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
  roles?: UserRole[];
}

const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard",          label: "Tổng quan",         icon: LayoutDashboard },
  { href: "/documents",          label: "Tài liệu",           icon: FileText },
  { href: "/documents/upload",   label: "Tải tài liệu lên",  icon: UploadCloud, roles: ["teacher", "admin"] },
  { href: "/folders",            label: "Thư mục",            icon: FolderTree,   roles: ["teacher", "admin"] },
  { href: "/search",             label: "Tìm kiếm",           icon: Search },
  { href: "/admin/users",        label: "Người dùng",         icon: Users,        roles: ["admin"] },
];

export function Sidebar({ role }: { role: UserRole }) {
  const pathname = usePathname();
  const items = NAV_ITEMS.filter((item) => !item.roles || item.roles.includes(role));

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-border/60 bg-card md:flex shadow-sm">
      {/* Brand */}
      <div className="flex h-14 items-center gap-2.5 border-b border-border/60 px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg gradient-brand text-white shadow-sm">
          <BookOpen className="h-4 w-4" />
        </div>
        <div>
          <span className="text-sm font-bold tracking-tight">SLRMS</span>
          <p className="text-[10px] leading-none text-muted-foreground mt-0.5">
            {role === "admin" ? "Quản trị viên" : role === "teacher" ? "Giáo viên" : "Học sinh"}
          </p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex flex-1 flex-col gap-0.5 p-2.5 pt-3">
        <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/70">
          Điều hướng
        </p>
        {items.map((item) => {
          const active =
            item.href === "/dashboard"
              ? pathname === "/dashboard"
              : pathname === item.href || pathname.startsWith(item.href + "/");
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group relative flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150",
                active
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground"
              )}
            >
              {active && (
                <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r bg-primary" />
              )}
              <Icon
                className={cn(
                  "h-4 w-4 shrink-0 transition-transform group-hover:scale-105",
                  active ? "text-primary" : "text-muted-foreground"
                )}
              />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-border/60 p-3">
        <p className="text-center text-[10px] text-muted-foreground/60">
          © 2024 SLRMS Platform
        </p>
      </div>
    </aside>
  );
}
