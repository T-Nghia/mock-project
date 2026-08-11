"use client";

import { useEffect, useState } from "react";
import { FileText, Users, TrendingUp } from "lucide-react";
import { dashboardApi } from "@/lib/api";
import type { DashboardResponse } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/dashboard/stat-card";
import { BarChart } from "@/components/dashboard/bar-chart";
import { useAuth } from "@/lib/auth-context";

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
      <div className="grid gap-5 md:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-24" />
        ))}
        <Skeleton className="h-64 md:col-span-3" />
      </div>
    );
  }

  if (!data) {
    return <p className="text-sm text-muted-foreground">Không thể tải dữ liệu tổng quan.</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">Chào mừng, {user?.full_name}</h2>
        <p className="text-sm text-muted-foreground">Đây là tổng quan hoạt động của bạn trong hệ thống.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3">
        <StatCard label="Tổng số tài liệu" value={data.summary.total_documents} icon={FileText} />
        {data.summary.total_users !== null && data.summary.total_users !== undefined && (
          <StatCard label="Tổng số người dùng" value={data.summary.total_users} icon={Users} />
        )}
        <StatCard
          label="Lượt tải lên gần đây"
          value={data.charts.uploads_by_day.reduce((sum, p) => sum + p.count, 0)}
          icon={TrendingUp}
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Tài liệu tải lên theo ngày</CardTitle>
          </CardHeader>
          <CardContent>
            <BarChart data={data.charts.uploads_by_day.map((p) => ({ label: p.date, value: p.count }))} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Tài liệu theo thư mục</CardTitle>
          </CardHeader>
          <CardContent>
            <BarChart data={data.charts.documents_by_folder.map((p) => ({ label: p.label, value: p.count }))} />
          </CardContent>
        </Card>

        {data.charts.users_by_role && (
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Người dùng theo vai trò</CardTitle>
            </CardHeader>
            <CardContent>
              <BarChart data={data.charts.users_by_role.map((p) => ({ label: p.label, value: p.count }))} />
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
