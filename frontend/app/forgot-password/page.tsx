"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { MailCheck } from "lucide-react";
import { authApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthFrame } from "@/components/auth/auth-frame";
import { FormError, formError } from "@/components/auth/form-error";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const busy = useRef(false);
  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (busy.current) return;
    busy.current = true; setError(null); setLoading(true);
    try { await authApi.forgotPassword(email); setSent(true); }
    catch (err) { setError(formError(err, "Không thể gửi yêu cầu. Vui lòng thử lại.")); }
    finally { busy.current = false; setLoading(false); }
  }
  return <AuthFrame title="Quên mật khẩu" description="Nhập email của bạn để yêu cầu liên kết đặt lại mật khẩu.">
    {sent ? <div role="status" className="space-y-4 rounded-xl border border-border bg-background p-5"><MailCheck aria-hidden="true" className="h-8 w-8 text-success" /><p className="font-semibold">Đã tiếp nhận yêu cầu</p><p className="break-words text-sm leading-7 text-muted-foreground">Nếu email {email} tồn tại trong hệ thống, hướng dẫn đặt lại mật khẩu sẽ được gửi đến hộp thư của bạn. Hãy kiểm tra cả thư mục thư rác.</p></div>
      : <form onSubmit={onSubmit} className="space-y-5" aria-label="Khôi phục mật khẩu"><FormError message={error} /><div className="space-y-2"><Label htmlFor="email">Email</Label><Input id="email" type="email" autoComplete="email" required disabled={loading} placeholder="ban@truong.edu.vn" value={email} onChange={(e) => setEmail(e.target.value)} /></div><Button type="submit" loading={loading} className="h-auto min-h-11 w-full whitespace-normal">{loading ? "Đang gửi yêu cầu…" : "Gửi liên kết đặt lại mật khẩu"}</Button></form>}
    <p className="mt-6 text-center"><Link href="/login" className="text-sm font-medium text-primary hover:underline">Quay lại đăng nhập</Link></p>
  </AuthFrame>;
}
