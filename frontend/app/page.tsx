"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Loader2 } from "lucide-react";

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.replace(user ? "/dashboard" : "/login");
  }, [loading, user, router]);

  return (
    <div role="status" className="flex min-h-dvh items-center justify-center gap-3">
      <Loader2 aria-hidden="true" className="h-6 w-6 animate-spin text-primary" />
      <span className="text-muted-foreground">Đang mở không gian học tập…</span>
    </div>
  );
}
