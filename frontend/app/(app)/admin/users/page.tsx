"use client";

import { useCallback, useEffect, useState } from "react";
import { UserPlus } from "lucide-react";
import { authApi, ApiError } from "@/lib/api";
import type { User, UserRole } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { initials, formatDate } from "@/lib/utils";
import { useToast } from "@/lib/toast-context";
import { useAuth } from "@/lib/auth-context";
import { CreateTeacherDialog } from "@/components/admin/create-teacher-dialog";

const ROLE_LABEL: Record<UserRole, string> = {
  admin: "Quản trị viên",
  teacher: "Giáo viên",
  student: "Học sinh",
};

export default function AdminUsersPage() {
  const { user: currentUser } = useAuth();
  const { toast } = useToast();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setUsers(await authApi.listUsers());
    } catch (err) {
      toast({ title: "Không tải được danh sách", description: err instanceof ApiError ? err.message : undefined, variant: "error" });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleRoleChange(u: User, role: UserRole) {
    try {
      await authApi.updateUserRole(u.id, role);
      toast({ title: "Đã cập nhật vai trò", variant: "success" });
      load();
    } catch (err) {
      toast({ title: "Cập nhật thất bại", description: err instanceof ApiError ? err.message : undefined, variant: "error" });
    }
  }

  async function handleStatusToggle(u: User) {
    try {
      await authApi.updateUserStatus(u.id, !u.is_active);
      toast({ title: u.is_active ? "Đã khoá tài khoản" : "Đã mở khoá tài khoản", variant: "success" });
      load();
    } catch (err) {
      toast({ title: "Cập nhật thất bại", description: err instanceof ApiError ? err.message : undefined, variant: "error" });
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle>Danh sách người dùng</CardTitle>
          <Button size="sm" onClick={() => setDialogOpen(true)}>
            <UserPlus className="h-4 w-4" /> Thêm giáo viên
          </Button>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex flex-col gap-2">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-11" />
              ))}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Người dùng</TableHead>
                  <TableHead>Vai trò</TableHead>
                  <TableHead>Trạng thái</TableHead>
                  <TableHead>Ngày tạo</TableHead>
                  <TableHead className="text-right">Hành động</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell>
                      <div className="flex items-center gap-2.5">
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                          {initials(u.full_name)}
                        </div>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">{u.full_name}</p>
                          <p className="truncate text-xs text-muted-foreground">{u.email}</p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Select
                        className="h-8 w-36 text-xs"
                        value={u.role}
                        disabled={u.id === currentUser?.id}
                        onChange={(e) => handleRoleChange(u, e.target.value as UserRole)}
                      >
                        {(Object.keys(ROLE_LABEL) as UserRole[]).map((r) => (
                          <option key={r} value={r}>
                            {ROLE_LABEL[r]}
                          </option>
                        ))}
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Badge variant={u.is_active ? "success" : "destructive"}>
                        {u.is_active ? "Đang hoạt động" : "Đã khoá"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{formatDate(u.created_at)}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={u.id === currentUser?.id}
                        onClick={() => handleStatusToggle(u)}
                      >
                        {u.is_active ? "Khoá" : "Mở khoá"}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <CreateTeacherDialog open={dialogOpen} onOpenChange={setDialogOpen} onCreated={load} />
    </div>
  );
}
