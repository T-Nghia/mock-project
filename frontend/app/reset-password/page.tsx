"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, GraduationCap } from "lucide-react";
import { authApi, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (newPassword !== confirmPassword) {
      setError("Mật khẩu nhập lại không khớp.");
      return;
    }
    if (!token) {
      setError("Liên kết không hợp lệ hoặc đã hết hạn. Vui lòng yêu cầu lại.");
      return;
    }

    setLoading(true);
    try {
      await authApi.resetPassword({
        token,
        new_password: newPassword,
        confirm_new_password: confirmPassword,
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không thể đặt lại mật khẩu. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader className="items-center text-center">
        <div className="mb-1 flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
          <GraduationCap className="h-6 w-6" />
        </div>
        <CardTitle className="text-xl">Đặt lại mật khẩu</CardTitle>
        <CardDescription>Nhập mật khẩu mới cho tài khoản của bạn</CardDescription>
      </CardHeader>
      <CardContent>
        {done ? (
          <div className="flex flex-col items-center gap-3 py-2 text-center">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-success/15 text-success">
              <CheckCircle2 className="h-5 w-5" />
            </div>
            <p className="text-sm text-muted-foreground">Mật khẩu đã được đặt lại thành công.</p>
            <Button className="mt-2 w-full" onClick={() => router.replace("/login")}>
              Đăng nhập ngay
            </Button>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            {!token && (
              <Alert variant="destructive">
                <AlertDescription>
                  Không tìm thấy mã đặt lại mật khẩu trong liên kết. Vui lòng dùng liên kết trong email.
                </AlertDescription>
              </Alert>
            )}
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="new_password">Mật khẩu mới</Label>
              <Input
                id="new_password"
                type="password"
                placeholder="Tối thiểu 8 ký tự"
                required
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="confirm_password">Nhập lại mật khẩu mới</Label>
              <Input
                id="confirm_password"
                type="password"
                placeholder="Nhập lại mật khẩu mới"
                required
                minLength={8}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </div>
            <Button type="submit" loading={loading} className="mt-1 w-full">
              Đặt lại mật khẩu
            </Button>
          </form>
        )}
        <p className="mt-5 text-center text-sm text-muted-foreground">
          <Link href="/login" className="font-medium text-primary hover:underline">
            Quay lại đăng nhập
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 px-4">
      <Suspense fallback={null}>
        <ResetPasswordForm />
      </Suspense>
    </div>
  );
}
