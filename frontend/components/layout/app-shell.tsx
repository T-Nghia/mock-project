"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

const TITLES: { match: (p: string) => boolean; title: string }[] = [
  { match: (p) => p === "/dashboard",                        title: "Tổng quan" },
  { match: (p) => p.startsWith("/documents/upload"),         title: "Tải tài liệu lên" },
  { match: (p) => p.startsWith("/documents/") && p !== "/documents/upload", title: "Chi tiết tài liệu" },
  { match: (p) => p === "/documents",                        title: "Tài liệu" },
  { match: (p) => p.startsWith("/folders"),                  title: "Thư mục" },
  { match: (p) => p.startsWith("/search"),                   title: "Tìm kiếm tài liệu" },
  { match: (p) => p.startsWith("/admin/users"),              title: "Quản lý người dùng" },
];

function pageTitle(pathname: string): string {
  return TITLES.find((t) => t.match(pathname))?.title ?? "SLRMS";
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  const restricted =
    pathname.startsWith("/admin") && user && user.role !== "admin";
  const teacherOnly =
    (pathname.startsWith("/folders") || pathname.startsWith("/documents/upload")) &&
    user &&
    user.role === "student";

  useEffect(() => {
    if (restricted || teacherOnly) router.replace("/dashboard");
  }, [restricted, teacherOnly, router]);

  if (loading || !user || restricted || teacherOnly) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Đang tải...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar role={user.role} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar title={pageTitle(pathname)} />
        <main className="flex-1 overflow-y-auto p-5 md:p-6">{children}</main>
      </div>
    </div>
  );
}
