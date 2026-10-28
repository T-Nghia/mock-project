"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/lib/toast-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { AuthFrame } from "@/components/auth/auth-frame";
import { FormError, formError } from "@/components/auth/form-error";

export default function RegisterPage() {
  const { register } = useAuth();
  const { toast } = useToast();
  const router = useRouter();
  const [form, setForm] = useState({ full_name: "", email: "", password: "", confirm_password: "" });
  const [error, setError] = useState<string | null>(null);
  const [mismatch, setMismatch] = useState(false);
  const [loading, setLoading] = useState(false);
  const busy = useRef(false);
  function update(key: keyof typeof form, value: string) { setForm((f) => ({ ...f, [key]: value })); setMismatch(false); }
  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (busy.current) return;
    setError(null);
    if (form.password !== form.confirm_password) { setMismatch(true); document.getElementById("confirm_password")?.focus(); return; }
    busy.current = true; setLoading(true);
    try {
      await register(form);
      toast({ title: "Đăng ký thành công", description: "Hãy đăng nhập để tiếp tục.", variant: "success" });
      router.push("/login");
    } catch (err) { setError(formError(err, "Đăng ký thất bại. Vui lòng thử lại.")); }
    finally { busy.current = false; setLoading(false); }
  }
  return <AuthFrame title="Tạo tài khoản học sinh" description="Bắt đầu xây dựng không gian học tập của riêng bạn. Tài khoản giáo viên do quản trị viên cấp.">
    <form onSubmit={onSubmit} className="space-y-4" aria-label="Đăng ký">
      <FormError message={error} />
      <div className="space-y-2"><Label htmlFor="full_name">Họ và tên</Label><Input id="full_name" autoComplete="name" required maxLength={255} disabled={loading} value={form.full_name} onChange={(e) => update("full_name", e.target.value)} /></div>
      <div className="space-y-2"><Label htmlFor="email">Email</Label><Input id="email" type="email" autoComplete="email" required disabled={loading} value={form.email} onChange={(e) => update("email", e.target.value)} /></div>
      <div className="space-y-2"><Label htmlFor="password">Mật khẩu</Label><PasswordInput id="password" autoComplete="new-password" required minLength={8} aria-describedby="password-help" disabled={loading} value={form.password} onChange={(e) => update("password", e.target.value)} /><p id="password-help" className="text-xs text-muted-foreground">Sử dụng ít nhất 8 ký tự.</p></div>
      <div className="space-y-2"><Label htmlFor="confirm_password">Xác nhận mật khẩu</Label><PasswordInput id="confirm_password" autoComplete="new-password" required minLength={8} aria-invalid={mismatch} aria-describedby={mismatch ? "confirm-error" : undefined} disabled={loading} value={form.confirm_password} onChange={(e) => update("confirm_password", e.target.value)} />{mismatch && <p id="confirm-error" role="alert" className="text-xs text-destructive">Mật khẩu xác nhận không khớp.</p>}</div>
      <Button type="submit" loading={loading} className="w-full">{loading ? "Đang tạo tài khoản…" : "Đăng ký"}</Button>
    </form>
    <p className="mt-6 border-t border-border pt-5 text-center text-sm text-muted-foreground">Đã có tài khoản? <Link href="/login" className="font-medium text-primary hover:underline">Đăng nhập</Link></p>
  </AuthFrame>;
}
