"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { BookOpen, Eye, EyeOff, GraduationCap, BookMarked, Users } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Đăng nhập thất bại. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* ─── Left: Brand Hero ─────────────────────────────── */}
      <div className="hidden lg:flex lg:w-1/2 gradient-brand relative flex-col items-center justify-center p-12 text-white overflow-hidden">
        {/* Decorative blobs */}
        <div className="absolute -top-24 -left-24 h-72 w-72 rounded-full bg-white/10 blur-3xl" />
        <div className="absolute -bottom-24 -right-24 h-72 w-72 rounded-full bg-white/10 blur-3xl" />

        <div className="relative z-10 max-w-sm text-center">
          <div className="mb-6 flex justify-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white/20 shadow-lg backdrop-blur-sm">
              <BookOpen className="h-8 w-8 text-white" />
            </div>
          </div>
          <h1 className="text-3xl font-bold tracking-tight mb-3">
            Hệ thống Quản lý<br />Tài liệu Học tập
          </h1>
          <p className="text-white/80 text-sm leading-relaxed mb-8">
            Nền tảng quản lý và chia sẻ tài liệu học tập thông minh, tích hợp AI hỗ trợ tìm kiếm và tóm tắt nội dung.
          </p>

          {/* Features */}
          <div className="flex flex-col gap-3 text-left">
            {[
              { icon: BookMarked, label: "Quản lý tài liệu theo thư mục" },
              { icon: GraduationCap, label: "Tìm kiếm thông minh full-text" },
              { icon: Users,       label: "Phân quyền Admin / Giáo viên / Học sinh" },
            ].map(({ icon: Icon, label }) => (
              <div key={label} className="flex items-center gap-3 rounded-xl bg-white/15 px-4 py-2.5 backdrop-blur-sm">
                <Icon className="h-4 w-4 shrink-0 text-white/90" />
                <span className="text-sm text-white/90">{label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ─── Right: Login Form ─────────────────────────────── */}
      <div className="flex flex-1 items-center justify-center bg-background px-6 py-12">
        <div className="w-full max-w-sm animate-fade-in">
          {/* Logo (mobile only) */}
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg gradient-brand text-white">
              <BookOpen className="h-5 w-5" />
            </div>
            <span className="text-lg font-bold">SLRMS</span>
          </div>

          <div className="mb-7">
            <h2 className="text-2xl font-bold tracking-tight">Đăng nhập</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Nhập thông tin tài khoản của bạn để tiếp tục.
            </p>
          </div>

          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            {error && (
              <Alert variant="destructive" className="animate-slide-up">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="ban@truong.edu.vn"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="password">Mật khẩu</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  required
                  minLength={8}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <Button type="submit" loading={loading} className="mt-1 w-full gradient-brand border-0 text-white hover:opacity-90">
              Đăng nhập
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            Chưa có tài khoản?{" "}
            <Link href="/register" className="font-semibold text-primary hover:underline">
              Đăng ký ngay
            </Link>
          </p>

          <p className="mt-3 text-center text-xs text-muted-foreground/70">
            Demo: admin@slrms.local / Admin@123
          </p>
        </div>
      </div>
    </div>
  );
}
