"use client";

import { useEffect, useState } from "react";
import { FileText, Users, TrendingUp, Upload, FolderOpen } from "lucide-react";
import { dashboardApi } from "@/lib/api";
import type { DashboardResponse } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/dashboard/stat-card";
import { BarChart } from "@/components/dashboard/bar-chart";
import { useAuth } from "@/lib/auth-context";

const GREETING = () => {
  const h = new Date().getHours();
  if (h < 12) return "Chào buổi sáng";
  if (h < 18) return "Chào buổi chiều";
  return "Chào buổi tối";
};

export default function DashboardPage() {
  const { user } = useAuth();
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    dashboardApi
      .get()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col gap-6 animate-fade-in">
        <Skeleton className="h-16 rounded-xl" />
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
        <div className="grid gap-5 lg:grid-cols-2">
          <Skeleton className="h-56 rounded-xl" />
          <Skeleton className="h-56 rounded-xl" />
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <p className="text-muted-foreground">Không thể tải dữ liệu tổng quan.</p>
      </div>
    );
  }

  const totalUploads = data.charts.uploads_by_day.reduce((s, p) => s + p.count, 0);

  return (
    <div className="flex flex-col gap-6 animate-fade-in">
      {/* ─── Welcome Banner ─────────────────────────────────── */}
      <div className="rounded-xl border bg-card p-5 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold tracking-tight">
              {GREETING()}, {user?.full_name?.split(" ").pop()} 👋
            </h2>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Đây là tổng quan hoạt động của hệ thống quản lý tài liệu học tập.
            </p>
          </div>
          <div className="hidden sm:flex h-12 w-12 items-center justify-center rounded-xl gradient-brand text-white shadow-sm">
            <TrendingUp className="h-6 w-6" />
          </div>
        </div>
      </div>

      {/* ─── Stat Cards ─────────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3">
        <StatCard
          label="Tổng số tài liệu"
          value={data.summary.total_documents}
          icon={FileText}
          description="Tài liệu đang lưu trữ"
          colorIndex={0}
        />
        {data.summary.total_users != null && (
          <StatCard
            label="Người dùng"
            value={data.summary.total_users}
            icon={Users}
            description="Tài khoản đã đăng ký"
            colorIndex={1}
          />
        )}
        <StatCard
          label="Tải lên gần đây"
          value={totalUploads}
          icon={Upload}
          description="Trong 7 ngày qua"
          colorIndex={2}
        />
      </div>

      {/* ─── Charts ─────────────────────────────────────────── */}
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold">
              <TrendingUp className="h-4 w-4 text-primary" />
              Tài liệu tải lên theo ngày
            </CardTitle>
          </CardHeader>
          <CardContent>
            <BarChart
              data={data.charts.uploads_by_day.map((p) => ({ label: p.date, value: p.count }))}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold">
              <FolderOpen className="h-4 w-4 text-primary" />
              Tài liệu theo thư mục
            </CardTitle>
          </CardHeader>
          <CardContent>
            <BarChart
              data={data.charts.documents_by_folder.map((p) => ({ label: p.label, value: p.count }))}
            />
          </CardContent>
        </Card>

        {data.charts.users_by_role && (
          <Card className="lg:col-span-2">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                <Users className="h-4 w-4 text-primary" />
                Người dùng theo vai trò
              </CardTitle>
            </CardHeader>
            <CardContent>
              <BarChart
                data={data.charts.users_by_role.map((p) => ({ label: p.label, value: p.count }))}
              />
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
