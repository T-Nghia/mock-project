"use client";

import { useEffect, useState } from "react";
import { UserPlus, Users } from "lucide-react";
import { authApi } from "@/lib/api";
import type { User, UserRole } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { PageLoading, PageState } from "@/components/ui/page-state";
import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";
import { initials, formatDate } from "@/lib/utils";
import { useToast } from "@/lib/toast-context";
import { useAuth } from "@/lib/auth-context";
import { CreateTeacherDialog } from "@/components/admin/create-teacher-dialog";

const ROLE_LABEL: Record<UserRole, string> = { admin: "Quản trị viên", teacher: "Giáo viên", student: "Học sinh" };
type Change = { user: User; role: UserRole } | { user: User; active: boolean };

export default function AdminUsersPage() {
  const { user: currentUser } = useAuth();
  const { toast } = useToast();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [change, setChange] = useState<Change | null>(null);
  useEffect(() => {
    if (currentUser?.role !== "admin") return;
    let cancelled = false;
    setLoading(true); setError(false);
    authApi.listUsers().then((items) => { if (!cancelled) setUsers(items); })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [currentUser?.role, currentUser?.id, attempt]);
  async function confirmChange() {
    if (!change) return;
    const updated = "role" in change ? await authApi.updateUserRole(change.user.id, change.role) : await authApi.updateUserStatus(change.user.id, change.active);
    setUsers((previous) => previous.map((user) => user.id === updated.id ? updated : user));
    toast({ title: "Đã cập nhật tài khoản", variant: "success" });
  }
  if (currentUser?.role !== "admin") return null;
  const description = !change ? "" : "role" in change ? `Đổi vai trò của ${change.user.full_name} (${change.user.email}) từ ${ROLE_LABEL[change.user.role]} sang ${ROLE_LABEL[change.role]}? Quyền truy cập của tài khoản sẽ thay đổi.` : `${change.active ? "Mở khoá" : "Khoá"} tài khoản ${change.user.full_name} (${change.user.email})? ${change.active ? "Tài khoản sẽ được phép truy cập trở lại." : "Người dùng sẽ không thể truy cập hệ thống khi tài khoản bị khoá."}`;
  return <div className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="mb-2 text-xs uppercase tracking-widest text-muted-foreground">Quản trị hệ thống</p><h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Quản lý người dùng</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">Quản lý tài khoản, vai trò và quyền truy cập vào SLRMS.</p></div><Button onClick={() => setDialogOpen(true)}><UserPlus aria-hidden="true" className="h-4 w-4" />Thêm giáo viên</Button></header>
    {loading ? <PageLoading label="Đang tải người dùng" /> : error ? <PageState title="Không tải được danh sách người dùng" description="Vui lòng thử lại. Những thay đổi chưa được xác nhận sẽ không được áp dụng." retry={() => setAttempt((v) => v + 1)} /> : !users.length ? <PageState title="Chưa có người dùng" description="Danh sách tài khoản hiện đang trống." /> : <>
      <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground"><Users aria-hidden="true" className="h-4 w-4" /><span>{users.length.toLocaleString("vi-VN")} tài khoản</span><span className="ml-auto text-xs">Không thể thay đổi tài khoản của chính bạn.</span></div>
      <ul aria-label="Danh sách người dùng" className="space-y-3">{users.map((user) => <li key={user.id} className="rounded-xl border border-border bg-card p-4 shadow-sm sm:p-5"><div className="grid min-w-0 items-center gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_auto]">
        <div className="flex min-w-0 items-start gap-3"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{initials(user.full_name)}</span><div className="min-w-0"><p className="break-words font-semibold">{user.full_name}{user.id === currentUser.id && <span className="ml-2 text-xs font-normal text-muted-foreground">(Bạn)</span>}</p><p className="mt-1 break-all text-xs text-muted-foreground">{user.email}</p><p className="mt-2 text-xs text-muted-foreground">Tạo {formatDate(user.created_at)}</p></div></div>
        <div className="min-w-0 space-y-2"><Badge variant={user.role === "admin" ? "default" : "secondary"}>{ROLE_LABEL[user.role]}</Badge><Select aria-label={`Vai trò của ${user.email}`} value={user.role} disabled={user.id === currentUser.id} onChange={(e) => { const role = e.target.value as UserRole; if (role !== user.role) setChange({ user, role }); }}>{(Object.keys(ROLE_LABEL) as UserRole[]).map((role) => <option key={role} value={role}>{ROLE_LABEL[role]}</option>)}</Select></div>
        <div><Badge variant={user.is_active ? "success" : "destructive"}>{user.is_active ? "Đang hoạt động" : "Đã khoá"}</Badge></div>
        <Button variant="outline" size="sm" disabled={user.id === currentUser.id} aria-label={`${user.is_active ? "Khoá" : "Mở khoá"} ${user.email}`} onClick={() => setChange({ user, active: !user.is_active })}>{user.is_active ? "Khoá" : "Mở khoá"}</Button>
      </div></li>)}</ul>
    </>}
    <CreateTeacherDialog open={dialogOpen} onOpenChange={setDialogOpen} onCreated={() => setAttempt((v) => v + 1)} />
    <ConfirmActionDialog open={!!change} onOpenChange={(open) => { if (!open) setChange(null); }} title={change && "role" in change ? "Xác nhận đổi vai trò" : "Xác nhận trạng thái tài khoản"} description={description} label="Xác nhận" destructive={!!change && "active" in change && !change.active} onConfirm={confirmChange} />
  </div>;
}
