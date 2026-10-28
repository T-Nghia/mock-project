"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { AuthFrame } from "@/components/auth/auth-frame";
import { FormError, formError } from "@/components/auth/form-error";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const busy = useRef(false);
  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (busy.current) return;
    busy.current = true; setError(null); setLoading(true);
    try { await login(email, password); router.replace("/dashboard"); }
    catch (err) { setError(formError(err, "Đăng nhập thất bại. Vui lòng thử lại.")); }
    finally { busy.current = false; setLoading(false); }
  }
  return <AuthFrame title="Đăng nhập SLRMS" description="Chào mừng trở lại. Tiếp tục hành trình học tập của bạn.">
    <form onSubmit={onSubmit} className="space-y-5" aria-label="Đăng nhập">
      <FormError message={error} />
      <div className="space-y-2"><Label htmlFor="email">Email</Label><Input id="email" type="email" autoComplete="email" placeholder="ban@truong.edu.vn" required disabled={loading} value={email} onChange={(e) => setEmail(e.target.value)} /></div>
      <div className="space-y-2"><Label htmlFor="password">Mật khẩu</Label><PasswordInput id="password" autoComplete="current-password" required minLength={8} disabled={loading} value={password} onChange={(e) => setPassword(e.target.value)} /><div className="text-right"><Link href="/forgot-password" className="inline-block py-1 text-xs font-medium text-primary hover:underline">Quên mật khẩu?</Link></div></div>
      <Button type="submit" loading={loading} className="w-full">{loading ? "Đang đăng nhập…" : "Đăng nhập"}</Button>
    </form>
    <p className="mt-6 border-t border-border pt-5 text-center text-sm text-muted-foreground">Chưa có tài khoản? <Link href="/register" className="font-medium text-primary hover:underline">Đăng ký ngay</Link></p>
  </AuthFrame>;
}
