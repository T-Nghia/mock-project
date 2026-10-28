"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, FolderTree, Library, UploadCloud, Users, GraduationCap, Bookmark, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import type { UserRole } from "@/lib/types";

interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
  roles?: UserRole[];
}

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Không gian làm việc",
    items: [
      { href: "/dashboard", label: "Tổng quan", icon: LayoutDashboard },
      { href: "/search", label: "Thư viện tài liệu", icon: Library },
      { href: "/bookmarks", label: "Đã lưu", icon: Bookmark },
    ],
  },
  {
    label: "Quản lý tài liệu",
    items: [
      { href: "/documents/upload", label: "Tải tài liệu lên", icon: UploadCloud, roles: ["teacher", "admin"] },
      { href: "/folders", label: "Thư mục", icon: FolderTree, roles: ["teacher"] },
    ],
  },
  {
    label: "Quản trị",
    items: [{ href: "/admin/users", label: "Người dùng", icon: Users, roles: ["admin"] }],
  },
];

interface SidebarProps {
  role: UserRole;
  collapsed?: boolean;
  mobile?: boolean;
  onToggle?: () => void;
  onNavigate?: () => void;
}

export function Sidebar({ role, collapsed = false, mobile = false, onToggle, onNavigate }: SidebarProps) {
  const pathname = usePathname();
  const compact = collapsed && !mobile;

  return (
    <aside
      aria-label="Thanh điều hướng"
      className={cn(
        "min-h-0 shrink-0 flex-col bg-sidebar transition-[width] duration-200 motion-reduce:transition-none",
        mobile ? "flex h-full w-full" : "hidden border-r border-border lg:flex",
        !mobile && (compact ? "w-16" : "w-60")
      )}
    >
      <div className={cn("flex h-16 shrink-0 items-center border-b border-border/70", compact ? "justify-center" : "px-5", mobile && "pr-14")}>
        <Link href="/dashboard" onClick={onNavigate} aria-label="SLRMS — Tổng quan" className="flex min-w-0 items-center gap-3 rounded-md">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
            <GraduationCap aria-hidden="true" className="h-5 w-5" strokeWidth={1.75} />
          </span>
          <span className={compact ? "sr-only" : "min-w-0"}>
            <span className="block text-[15px] font-bold leading-5 tracking-tight">SLRMS</span>
            <span className="block truncate text-[11px] leading-4 text-muted-foreground">Không gian học tập</span>
          </span>
        </Link>
      </div>

      <nav id={mobile ? "mobile-navigation-links" : "desktop-navigation"} aria-label="Điều hướng chính" className={cn("min-h-0 flex-1 space-y-6 overflow-y-auto py-6", compact ? "px-2" : "px-3")}>
        {NAV_GROUPS.map((group) => {
          const items = group.items.filter((item) => !item.roles || item.roles.includes(role));
          if (items.length === 0) return null;
          return (
            <div key={group.label}>
              <p className={cn("mb-2 px-3 text-[11px] font-medium tracking-wide text-muted-foreground", compact && "sr-only")}>
                {group.label}
              </p>
              <ul className="space-y-1">
                {items.map((item) => {
                  const active = pathname === item.href || pathname.startsWith(item.href + "/");
                  const relatedDocument = item.href === "/search" && pathname.startsWith("/documents/") && !pathname.startsWith("/documents/upload");
                  const Icon = item.icon;
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        onClick={onNavigate}
                        aria-current={active ? "page" : undefined}
                        title={compact ? item.label : undefined}
                        className={cn(
                          "flex min-h-11 items-center gap-3 rounded-md text-sm font-medium transition-colors duration-150",
                          compact ? "justify-center px-2" : "px-3",
                          active || relatedDocument
                            ? "bg-primary/[0.08] text-primary ring-1 ring-inset ring-primary/10"
                            : "text-muted-foreground hover:bg-accent hover:text-foreground"
                        )}
                      >
                        <Icon aria-hidden="true" className="h-[18px] w-[18px] shrink-0" strokeWidth={1.75} />
                        <span className={compact ? "sr-only" : "truncate"}>{item.label}</span>
                        {(active || relatedDocument) && !compact && <span aria-hidden="true" className="ml-auto h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>

      <div className={cn("shrink-0 border-t border-border/70", compact ? "p-2" : "p-3")}>
        {!mobile && (
          <button
            type="button"
            onClick={onToggle}
            aria-label={compact ? "Mở rộng thanh điều hướng" : "Thu gọn thanh điều hướng"}
            aria-expanded={!compact}
            aria-controls="desktop-navigation"
            title={compact ? "Mở rộng thanh điều hướng" : undefined}
            className={cn("flex min-h-11 w-full items-center gap-3 rounded-md text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground", compact ? "justify-center" : "px-3")}
          >
            {compact ? <PanelLeftOpen aria-hidden="true" className="h-[18px] w-[18px]" /> : <PanelLeftClose aria-hidden="true" className="h-[18px] w-[18px]" />}
            {!compact && <span>Thu gọn thanh bên</span>}
          </button>
        )}
        {mobile && <p className="px-3 py-2 text-xs leading-relaxed text-muted-foreground">Tài nguyên học tập, cùng một nơi.</p>}
      </div>
    </aside>
  );
}
