"use client";

import { Suspense, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2 } from "lucide-react";
import { authApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { AuthFrame } from "@/components/auth/auth-frame";
import { FormError, formError } from "@/components/auth/form-error";

function ResetPasswordForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [mismatch, setMismatch] = useState(false);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const busy = useRef(false);
  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (busy.current || !token) return;
    setError(null);
    if (newPassword !== confirmPassword) { setMismatch(true); document.getElementById("confirm_password")?.focus(); return; }
    busy.current = true; setLoading(true);
    try { await authApi.resetPassword({ token, new_password: newPassword, confirm_new_password: confirmPassword }); setDone(true); }
    catch (err) { setError(formError(err, "Không thể đặt lại mật khẩu. Vui lòng thử lại.")); }
    finally { busy.current = false; setLoading(false); }
  }
  return <>
    {done ? <div className="space-y-5"><div role="status" className="space-y-3 rounded-xl border border-border bg-background p-5"><CheckCircle2 aria-hidden="true" className="h-8 w-8 text-success" /><p>Mật khẩu đã được đặt lại thành công.</p></div><Button className="w-full" onClick={() => router.replace("/login")}>Đăng nhập ngay</Button></div>
      : !token ? <FormError message="Không tìm thấy mã đặt lại mật khẩu trong liên kết. Vui lòng dùng liên kết trong email hoặc yêu cầu liên kết mới." />
      : <form onSubmit={onSubmit} className="space-y-5" aria-label="Đặt lại mật khẩu"><FormError message={error} />
        <div className="space-y-2"><Label htmlFor="new_password">Mật khẩu mới</Label><PasswordInput id="new_password" required minLength={8} autoComplete="new-password" disabled={loading} aria-describedby="password-help" value={newPassword} onChange={(e) => { setNewPassword(e.target.value); setMismatch(false); }} /><p id="password-help" className="text-xs text-muted-foreground">Sử dụng ít nhất 8 ký tự.</p></div>
        <div className="space-y-2"><Label htmlFor="confirm_password">Nhập lại mật khẩu mới</Label><PasswordInput id="confirm_password" required minLength={8} autoComplete="new-password" disabled={loading} aria-invalid={mismatch} aria-describedby={mismatch ? "confirm-error" : undefined} value={confirmPassword} onChange={(e) => { setConfirmPassword(e.target.value); setMismatch(false); }} />{mismatch && <p id="confirm-error" role="alert" className="text-xs text-destructive">Mật khẩu nhập lại không khớp.</p>}</div>
        <Button type="submit" loading={loading} className="w-full">{loading ? "Đang cập nhật…" : "Đặt lại mật khẩu"}</Button>
      </form>}
    {!done && <p className="mt-5 text-center"><Link href="/forgot-password" className="text-sm text-primary hover:underline">Yêu cầu liên kết mới</Link></p>}
    <p className="mt-5 text-center"><Link href="/login" className="text-sm font-medium text-primary hover:underline">Quay lại đăng nhập</Link></p>
  </>;
}
export default function ResetPasswordPage() {
  return <AuthFrame title="Đặt lại mật khẩu" description="Chọn mật khẩu mới để tiếp tục truy cập không gian học tập."><Suspense fallback={<p role="status">Đang tải biểu mẫu…</p>}><ResetPasswordForm /></Suspense></AuthFrame>;
}
