"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowRight, Bookmark, BookOpen, CalendarDays, FileText, FolderTree, Library, Search, UploadCloud, Users } from "lucide-react";
import { ApiError, dashboardApi } from "@/lib/api";
import type { DashboardResponse, UserRole } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/dashboard/stat-card";
import { BarChart } from "@/components/dashboard/bar-chart";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

const ROLE_LABELS: Record<UserRole, string> = { student: "Học sinh", teacher: "Giáo viên", admin: "Quản trị viên" };

// API dates are calendar days in UTC; don't reinterpret them in the browser timezone.
function dateLabel(date: string, includeYear = false) {
  const [year, month, day] = date.split("-");
  return includeYear ? `${day}/${month}/${year}` : `${day}/${month}`;
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const role = user?.role;
  const canViewAnalytics = role === "teacher" || role === "admin";
  const isAdmin = role === "admin";

  useEffect(() => {
    // The existing backend deliberately denies students access to dashboard metrics.
    if (!canViewAnalytics) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    dashboardApi.get()
      .then((response) => { if (!cancelled) setData(response); })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError && err.status === 403
          ? "Bạn không có quyền xem thống kê này."
          : "Chưa thể lấy dữ liệu tổng quan. Vui lòng thử lại sau.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [canViewAnalytics, user?.id, role, attempt]);

  if (!user) return null;

  const uploads = data?.charts.uploads_by_day ?? [];
  const period = uploads.length > 0
    ? `${dateLabel(uploads[0].date, true)} – ${dateLabel(uploads[uploads.length - 1].date, true)}`
    : "7 ngày gần nhất";
  const metricsColumns = isAdmin ? "sm:grid-cols-2 xl:grid-cols-3" : "sm:grid-cols-2";
  const actions = [
    { href: "/search", label: "Thư viện tài liệu", description: "Tìm kiếm theo tiêu đề, thẻ hoặc môn học.", icon: Library },
    { href: "/bookmarks", label: "Tài liệu đã lưu", description: "Trở lại những tài liệu bạn đã đánh dấu.", icon: Bookmark },
    ...(canViewAnalytics ? [
      { href: "/documents/upload", label: "Tải tài liệu lên", description: "Thêm tài nguyên mới vào không gian học tập.", icon: UploadCloud },
    ] : []),
    ...(user.role === "teacher" ? [{ href: "/folders", label: "Thư mục", description: "Sắp xếp và quản lý tài liệu học tập.", icon: FolderTree }] : []),
    ...(isAdmin ? [{ href: "/admin/users", label: "Quản lý người dùng", description: "Quản lý tài khoản và vai trò trong hệ thống.", icon: Users }] : []),
  ];

  return (
    <div className="flex min-w-0 flex-col gap-7">
      <header className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">Không gian học tập</span>
            <Badge variant="secondary">{ROLE_LABELS[user.role]}</Badge>
          </div>
          <h2 className="break-words text-2xl font-semibold leading-tight tracking-tight sm:text-3xl">Chào mừng, {user.full_name || "bạn"}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            {isAdmin ? "Theo dõi tài nguyên và người dùng trong hệ thống SLRMS." : canViewAnalytics ? "Theo dõi tài liệu của bạn và chuẩn bị cho những buổi học tiếp theo." : "Khám phá tài liệu, lưu kiến thức và học cùng trợ lý AI."}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Link href="/search" className={buttonVariants({ variant: canViewAnalytics ? "outline" : "default" })}><Search aria-hidden="true" className="h-4 w-4" />Tìm kiếm tài liệu</Link>
          {canViewAnalytics && <Link href="/documents/upload" className={buttonVariants()}><UploadCloud aria-hidden="true" className="h-4 w-4" />Tải tài liệu lên</Link>}
        </div>
      </header>

      {canViewAnalytics ? (
        <section aria-label="Thống kê tổng quan" aria-busy={loading} className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">{isAdmin ? "Tổng quan hệ thống" : "Tổng quan tài liệu của bạn"}</h3>
            <span className="text-xs text-muted-foreground">{isAdmin ? "Phạm vi: toàn hệ thống" : "Phạm vi: tài liệu do bạn tải lên"}</span>
          </div>
          {loading ? (
            <div role="status" aria-label="Đang tải thống kê" className="space-y-5">
              <span className="sr-only">Đang tải thống kê…</span>
              <div className={cn("grid gap-4", metricsColumns)}>
                {Array.from({ length: isAdmin ? 3 : 2 }, (_, index) => <Card key={index} className="min-h-[156px] p-5"><Skeleton className="mb-5 h-4 w-32" /><Skeleton className="mb-3 h-9 w-20" /><Skeleton className="h-3 w-40 max-w-full" /></Card>)}
              </div>
              <div className="grid gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
                {[0, 1].map((index) => <Card key={index} className="min-h-[360px] p-5"><Skeleton className="h-5 w-40 max-w-full" /><Skeleton className="mt-3 h-3 w-48 max-w-full" /><Skeleton className="mt-8 h-56 w-full" /></Card>)}
              </div>
              {isAdmin && <Card className="min-h-[260px] p-5"><Skeleton className="mb-6 h-5 w-40" /><Skeleton className="h-40 w-full" /></Card>}
            </div>
          ) : error || !data ? (
            <Card className="flex min-h-72 flex-col items-center justify-center gap-4 px-5 py-10 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-destructive/5 text-destructive"><AlertCircle aria-hidden="true" className="h-6 w-6" /></span>
              <div role="alert"><h3 className="font-semibold">Không tải được thống kê</h3><p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">{error ?? "Vui lòng thử lại sau."}</p></div>
              <Button variant="outline" onClick={() => setAttempt((value) => value + 1)}>Thử lại</Button>
            </Card>
          ) : (
            <>
              <div className={cn("grid gap-4", metricsColumns)}>
                <StatCard label="Tổng số tài liệu" value={data.summary.total_documents} icon={FileText} description={isAdmin ? "Tài liệu hiện có trong hệ thống" : "Tài liệu do bạn tải lên"} />
                <StatCard label="Tài liệu tải lên trong 7 ngày" value={uploads.reduce((sum, point) => sum + point.count, 0)} icon={CalendarDays} description="7 ngày gần nhất, tính theo UTC" />
                {isAdmin && data.summary.total_users != null && <StatCard label="Tổng số người dùng" value={data.summary.total_users} icon={Users} description="Tài khoản hiện có trong hệ thống" />}
              </div>
              {data.summary.total_documents === 0 && <div className="flex flex-col gap-3 rounded-lg border border-primary/15 bg-primary/5 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div><p className="text-sm font-semibold">{isAdmin ? "Hệ thống chưa có tài liệu" : "Bạn chưa tải tài liệu nào lên"}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">Bắt đầu với tài liệu đầu tiên để xây dựng không gian học tập.</p></div>
                <Link href="/documents/upload" className={buttonVariants({ variant: "outline", size: "sm", className: "w-fit" })}>Tải tài liệu đầu tiên<ArrowRight aria-hidden="true" className="h-3.5 w-3.5" /></Link>
              </div>}
              <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
                <Card className="min-h-[360px]">
                  <CardHeader><CardTitle>Tài liệu tải lên theo ngày</CardTitle><CardDescription className="flex flex-wrap items-center gap-x-2 text-xs leading-5"><span>{period}</span><span>· UTC</span></CardDescription></CardHeader>
                  <CardContent>
                    <BarChart label="Số tài liệu tải lên theo ngày" orientation="vertical" data={uploads.map((point) => ({ label: dateLabel(point.date), description: `Ngày ${dateLabel(point.date, true)}`, value: point.count }))} emptyMessage="Chưa có tài liệu tải lên trong 7 ngày này." />
                  </CardContent>
                </Card>
                <Card className="min-h-[360px]">
                  <CardHeader><CardTitle>Tài liệu theo thư mục</CardTitle><CardDescription className="text-xs leading-5">Phân bố tài liệu theo tên thư mục</CardDescription></CardHeader>
                  <CardContent><BarChart label="Số tài liệu theo thư mục" data={data.charts.documents_by_folder.map((point) => ({ label: point.label === "Uncategorized" ? "Chưa phân loại" : point.label, value: point.count }))} emptyMessage="Chưa có tài liệu để thống kê theo thư mục." /></CardContent>
                </Card>
              </div>
              {isAdmin && data.charts.users_by_role != null && <Card className="min-h-[260px]">
                <CardHeader><CardTitle>Người dùng theo vai trò</CardTitle><CardDescription className="text-xs leading-5">Cơ cấu tài khoản trong toàn hệ thống</CardDescription></CardHeader>
                <CardContent><BarChart label="Số người dùng theo vai trò" unit="người dùng" data={data.charts.users_by_role.map((point) => ({ label: ROLE_LABELS[point.label as UserRole] ?? point.label, value: point.count }))} emptyMessage="Chưa có dữ liệu người dùng theo vai trò." /></CardContent>
              </Card>}
            </>
          )}
        </section>
      ) : (
        <Card className="overflow-hidden">
          <CardContent className="grid gap-8 p-5 sm:p-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:items-center">
            <div>
              <span className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary"><BookOpen aria-hidden="true" className="h-6 w-6" strokeWidth={1.75} /></span>
              <h3 className="text-xl font-semibold tracking-tight">Bắt đầu từ một tài liệu</h3>
              <p className="mt-3 max-w-xl text-sm leading-7 text-muted-foreground">Tìm nội dung bạn quan tâm, đọc tài liệu và đặt câu hỏi cho trợ lý AI khi tài liệu đã xử lý xong. Lưu lại những tài liệu hữu ích để dễ dàng tiếp tục học.</p>
              <Link href="/search" className={buttonVariants({ variant: "outline", className: "mt-5" })}>Khám phá thư viện<ArrowRight aria-hidden="true" className="h-4 w-4" /></Link>
            </div>
            <ol aria-label="Bắt đầu học với SLRMS" className="space-y-5 rounded-xl bg-background p-5">
              {[{ title: "Tìm tài liệu", text: "Tra cứu theo tiêu đề, thẻ hoặc môn học." }, { title: "Đọc và đặt câu hỏi", text: "Đối chiếu câu trả lời AI với nguồn trích dẫn." }, { title: "Lưu để học tiếp", text: "Đánh dấu tài liệu và trở lại khi cần." }].map((step, index) => <li key={step.title} className="flex items-start gap-3"><span aria-hidden="true" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border bg-card text-xs font-medium text-primary">{index + 1}</span><div><p className="text-sm font-medium">{step.title}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">{step.text}</p></div></li>)}
            </ol>
          </CardContent>
        </Card>
      )}

      <nav aria-label="Truy cập nhanh">
        <h3 className="mb-1 text-base font-semibold tracking-tight">Truy cập nhanh</h3>
        <p className="mb-4 text-xs leading-5 text-muted-foreground">Những công cụ cho công việc và học tập của bạn.</p>
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {actions.map((action) => <li key={action.href} className="min-w-0"><Link href={action.href} className="group flex h-full items-start gap-3 rounded-lg border border-border bg-card p-4 shadow-sm transition-colors hover:border-primary/30 hover:bg-primary/[0.02]">
            <action.icon aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-primary" strokeWidth={1.75} />
            <div className="min-w-0 flex-1"><span className="block text-sm font-medium">{action.label}</span><span className="mt-1 block text-xs leading-5 text-muted-foreground">{action.description}</span></div>
            <ArrowRight aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground group-hover:text-primary" />
          </Link></li>)}
        </ul>
      </nav>
    </div>
  );
}
