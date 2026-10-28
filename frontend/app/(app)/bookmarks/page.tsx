"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bookmark, FileText, ChevronLeft, ChevronRight } from "lucide-react";
import { socialApi } from "@/lib/api";
import type { PaginatedBookmarks } from "@/lib/types";
import { Button, buttonVariants } from "@/components/ui/button";
import { PageLoading, PageState } from "@/components/ui/page-state";
import { StatusBadge } from "@/components/documents/status-badge";
import { formatDate } from "@/lib/utils";
import { useToast } from "@/lib/toast-context";

export default function BookmarksPage() {
  const { toast } = useToast();
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [data, setData] = useState<PaginatedBookmarks | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const lock = useRef(false);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(false);
    socialApi.listMyBookmarks(page, 20)
      .then((res) => { if (!cancelled) setData(res); })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [page, attempt]);
  async function remove(id: string) {
    if (lock.current) return;
    lock.current = true; setRemoving(id);
    try {
      await socialApi.removeBookmark(id);
      // Do not optimistically remove items: keep the list intact on a failed request.
      setData((previous) => previous ? { ...previous, items: previous.items.filter((doc) => doc.id !== id), total: Math.max(0, previous.total - 1) } : previous);
      toast({ title: "Đã bỏ lưu tài liệu", variant: "success" });
      if (data?.items.length === 1 && page > 1) setPage(page - 1);
      else setAttempt((value) => value + 1);
    } catch { toast({ title: "Không thể bỏ lưu", description: "Tài liệu vẫn được giữ trong danh sách. Vui lòng thử lại.", variant: "error" }); }
    finally { lock.current = false; setRemoving(null); }
  }
  return <div className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="mb-2 text-xs uppercase tracking-widest text-muted-foreground">Bộ sưu tập cá nhân</p><h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Tài liệu đã lưu</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">Trở lại những tài nguyên bạn muốn đọc và khám phá thêm.</p></div><Link href="/search" className={buttonVariants({ variant: "outline" })}>Khám phá thư viện</Link></header>
    {loading ? <PageLoading label="Đang tải tài liệu đã lưu" /> : error ? <PageState title="Không tải được tài liệu đã lưu" description="Vui lòng thử lại để cập nhật danh sách của bạn." retry={() => setAttempt((v) => v + 1)} /> : !data?.items.length ? <PageState title={page > 1 ? "Trang này không còn tài liệu" : "Bạn chưa lưu tài liệu nào"} description="Mở một tài liệu trong thư viện và chọn Lưu để dễ tìm lại tại đây.">{page > 1 ? <Button onClick={() => setPage(1)}>Về trang đầu</Button> : <Link href="/search" className={buttonVariants()}>Tìm tài liệu</Link>}</PageState> : <>
      <p role="status" className="text-sm text-muted-foreground">{data.total.toLocaleString("vi-VN")} tài liệu đã lưu</p>
      <ul className="space-y-3">{data.items.map((doc) => <li key={doc.id} className="rounded-xl border border-border bg-card p-4 shadow-sm sm:p-5"><div className="flex min-w-0 items-start gap-3"><FileText aria-hidden="true" className="mt-1 h-5 w-5 shrink-0 text-primary" /><div className="min-w-0 flex-1"><Link href={`/documents/${doc.id}`} className="break-words text-base font-semibold leading-6 hover:text-primary hover:underline">{doc.title}</Link><p className="mt-2 text-xs leading-6 text-muted-foreground">{doc.file_type.toUpperCase()} · Đã lưu {formatDate(doc.bookmarked_at)}</p><div className="mt-3 flex flex-wrap items-center justify-between gap-3"><StatusBadge status={doc.processing_status} /><Button variant="ghost" size="sm" loading={removing === doc.id} disabled={!!removing} aria-label={`Bỏ lưu ${doc.title}`} onClick={() => remove(doc.id)}><Bookmark aria-hidden="true" className="h-4 w-4" />Bỏ lưu</Button></div></div></div></li>)}</ul>
      <nav aria-label="Phân trang tài liệu đã lưu" className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4"><p className="text-xs text-muted-foreground">Trang {data.page}/{Math.max(1, Math.ceil(data.total / data.page_size))}</p><div className="flex gap-2"><Button variant="outline" size="sm" disabled={page === 1 || !!removing} onClick={() => setPage(page - 1)}><ChevronLeft aria-hidden="true" className="h-4 w-4" />Trước</Button><Button variant="outline" size="sm" disabled={page * data.page_size >= data.total || !!removing} onClick={() => setPage(page + 1)}>Tiếp theo<ChevronRight aria-hidden="true" className="h-4 w-4" /></Button></div></nav>
    </>}
  </div>;
}
