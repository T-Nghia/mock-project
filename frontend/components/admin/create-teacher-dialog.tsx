"use client";

import { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { authApi } from "@/lib/api";
import { PasswordInput } from "@/components/ui/password-input";
import { formError } from "@/components/auth/form-error";
import { useToast } from "@/lib/toast-context";

export function CreateTeacherDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}) {
  const { toast } = useToast();
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const lock = useRef(false);
  useEffect(() => { if (open) setError(null); }, [open]);
  function close(value: boolean) { if (!lock.current) onOpenChange(value); }

  function update(key: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (lock.current) return;
    lock.current = true;
    setError(null);
    setLoading(true);
    try {
      await authApi.createTeacher(form);
      toast({ title: "Đã tạo tài khoản giáo viên", variant: "success" });
      setForm({ full_name: "", email: "", password: "" });
      onOpenChange(false);
      onCreated();
    } catch (err) {
      setError(formError(err, "Tạo tài khoản thất bại. Vui lòng thử lại."));
    } finally {
      lock.current = false;
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent onClose={loading ? undefined : () => close(false)}>
        <DialogHeader>
          <DialogTitle>Thêm tài khoản giáo viên</DialogTitle>
          <p className="text-sm leading-6 text-muted-foreground">Tạo tài khoản để giáo viên tải lên và quản lý tài nguyên học tập.</p>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="t-name">Họ và tên</Label>
            <Input id="t-name" required maxLength={255} disabled={loading} autoComplete="off" value={form.full_name} onChange={(e) => update("full_name", e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="t-email">Email</Label>
            <Input id="t-email" type="email" required disabled={loading} autoComplete="off" value={form.email} onChange={(e) => update("email", e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="t-password">Mật khẩu tạm thời</Label>
            <PasswordInput
              id="t-password"
              type="password"
              disabled={loading}
              autoComplete="new-password"
              aria-describedby="teacher-password-help"
              required
              minLength={8}
              value={form.password}
              onChange={(e) => update("password", e.target.value)}
            />
            <p id="teacher-password-help" className="text-xs text-muted-foreground">Ít nhất 8 ký tự. Chia sẻ thông tin đăng nhập riêng với giáo viên.</p>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" disabled={loading} onClick={() => close(false)}>
              Huỷ
            </Button>
            <Button type="submit" loading={loading}>
              Tạo tài khoản
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
