"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const TITLES: { match: (p: string) => boolean; title: string }[] = [
  { match: (p) => p.startsWith("/dashboard"), title: "Tổng quan" },
  { match: (p) => p.startsWith("/documents/upload"), title: "Tải tài liệu lên" },
  { match: (p) => p.startsWith("/documents/"), title: "Chi tiết tài liệu" },
  { match: (p) => p.startsWith("/folders"), title: "Thư mục" },
  { match: (p) => p.startsWith("/search"), title: "Tìm kiếm tài liệu" },
  { match: (p) => p.startsWith("/bookmarks"), title: "Tài liệu đã lưu" },
  { match: (p) => p.startsWith("/admin/users"), title: "Quản lý người dùng" },
];

function pageTitle(pathname: string): string {
  return TITLES.find((t) => t.match(pathname))?.title ?? "SLRMS";
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const documentWorkspace = /^\/documents\/[^/]+$/.test(pathname) && pathname !== "/documents/upload";
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    // A layout preference only; authentication stays in AuthProvider.
    try {
      setCollapsed(localStorage.getItem("slrms.sidebar.collapsed") === "true");
    } catch {
      // Navigation remains usable when browser storage is unavailable.
    }
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 1024px)");
    const closeOnDesktop = () => {
      if (desktop.matches) setMobileOpen(false);
    };
    desktop.addEventListener("change", closeOnDesktop);
    return () => desktop.removeEventListener("change", closeOnDesktop);
  }, []);

  function toggleSidebar() {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem("slrms.sidebar.collapsed", String(next));
    } catch {
      // Persisting this preference is optional.
    }
  }

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  const restricted = pathname.startsWith("/admin") && user && user.role !== "admin";
  const teacherOnly =
    (pathname.startsWith("/folders") || pathname.startsWith("/documents/upload")) &&
    user &&
    user.role === "student";

  useEffect(() => {
    if (restricted || teacherOnly) router.replace("/dashboard");
  }, [restricted, teacherOnly, router]);

  if (loading || !user || restricted || teacherOnly) {
    return (
      <div role="status" className="flex min-h-dvh items-center justify-center gap-3 text-muted-foreground">
        <Loader2 aria-hidden="true" className="h-5 w-5 animate-spin text-primary" />
        <span>Đang tải không gian học tập…</span>
      </div>
    );
  }

  return (
    <div className="flex h-dvh overflow-hidden bg-background">
      <a href="#main-content" className="skip-link">Chuyển đến nội dung chính</a>
      <Sidebar role={user.role} collapsed={collapsed} onToggle={toggleSidebar} />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <Topbar title={pageTitle(pathname)} mobileOpen={mobileOpen} onOpenNavigation={() => setMobileOpen(true)} />
        <main id="main-content" tabIndex={-1} className={cn("min-h-0 min-w-0 flex-1 outline-none", documentWorkspace ? "overflow-hidden p-3 sm:p-4 lg:p-5" : "overflow-y-auto overscroll-contain p-4 sm:p-6 lg:p-8")}>
          <div className={cn("mx-auto w-full min-w-0", documentWorkspace ? "h-full" : "max-w-[1440px]")}>{children}</div>
        </main>
      </div>
      <Dialog id="mobile-navigation" open={mobileOpen} onOpenChange={setMobileOpen} variant="drawer">
        <DialogContent className="flex h-full max-w-none flex-col rounded-none border-0 border-r bg-sidebar p-0 sm:p-0" onClose={() => setMobileOpen(false)}>
          <DialogTitle className="sr-only">Điều hướng SLRMS</DialogTitle>
          <Sidebar role={user.role} mobile onNavigate={() => setMobileOpen(false)} />
        </DialogContent>
      </Dialog>
    </div>
  );
}
