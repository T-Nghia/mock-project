"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronLeft, ChevronRight, MessageSquare, Trash2 } from "lucide-react";
import { chatApi } from "@/lib/api";
import type { ChatSession, PaginatedChatSessions } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";
import { PageLoading, PageState } from "@/components/ui/page-state";
import { formatDate } from "@/lib/utils";

const PAGE_SIZE = 20;

export default function ChatHistoryPage() {
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [data, setData] = useState<PaginatedChatSessions | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [selected, setSelected] = useState<ChatSession | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    chatApi.listSessions(PAGE_SIZE, offset)
      .then((result) => { if (!cancelled) setData(result); })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [offset, attempt]);

  async function deleteSelected() {
    if (!selected) return;
    await chatApi.deleteSession(selected.id);
    if (data?.items.length === 1 && offset > 0) setOffset(Math.max(0, offset - PAGE_SIZE));
    else setAttempt((value) => value + 1);
  }

  return <div className="space-y-6">
    <header>
      <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Lịch sử trò chuyện</h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">Các cuộc trò chuyện của bạn được giữ khi tài liệu bị xóa. Bạn có thể đọc lại hoặc xóa từng cuộc trò chuyện tại đây.</p>
    </header>
    {loading ? <PageLoading label="Đang tải lịch sử trò chuyện" /> : error ? (
      <PageState title="Không tải được lịch sử trò chuyện" description="Vui lòng thử lại để xem các cuộc trò chuyện của bạn." retry={() => setAttempt((value) => value + 1)} />
    ) : !data?.items.length ? (
      <PageState title="Chưa có cuộc trò chuyện nào" description="Các cuộc trò chuyện bạn tạo trong không gian tài liệu sẽ xuất hiện tại đây.">
        {offset > 0 && <Button onClick={() => setOffset(0)}>Về trang đầu</Button>}
      </PageState>
    ) : <>
      <p role="status" className="text-sm text-muted-foreground">{data.total.toLocaleString("vi-VN")} cuộc trò chuyện</p>
      <ul className="space-y-3">{data.items.map((session) => <li key={session.id} className="rounded-xl border border-border bg-card p-4 sm:p-5">
        <div className="flex min-w-0 items-start gap-3">
          <MessageSquare aria-hidden="true" className="mt-1 h-5 w-5 shrink-0 text-primary" />
          <div className="min-w-0 flex-1">
            <Link href={`/chat/${session.id}`} className="break-words font-semibold leading-6 hover:text-primary hover:underline">{session.title || "Cuộc trò chuyện mới"}</Link>
            <p className="mt-2 text-xs leading-6 text-muted-foreground">{formatDate(session.created_at)}</p>
            {session.document_id === null && <p className="mt-1 text-xs text-muted-foreground">Tài liệu đã xóa · Chỉ đọc</p>}
          </div>
          <Button variant="ghost" size="icon" onClick={() => setSelected(session)} aria-label={`Xóa cuộc trò chuyện ${session.title || "Cuộc trò chuyện mới"}`}><Trash2 aria-hidden="true" className="h-4 w-4" /></Button>
        </div>
      </li>)}</ul>
      <nav aria-label="Phân trang lịch sử trò chuyện" className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
        <p className="text-xs text-muted-foreground">Trang {Math.floor(data.offset / PAGE_SIZE) + 1}/{Math.max(1, Math.ceil(data.total / PAGE_SIZE))}</p>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}><ChevronLeft aria-hidden="true" className="h-4 w-4" />Trước</Button>
          <Button variant="outline" size="sm" disabled={offset + data.limit >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Tiếp theo<ChevronRight aria-hidden="true" className="h-4 w-4" /></Button>
        </div>
      </nav>
    </>}
    <ConfirmActionDialog open={!!selected} onOpenChange={(open) => { if (!open) setSelected(null); }} title="Xóa cuộc trò chuyện?"
      description={`Xóa vĩnh viễn “${selected?.title || "Cuộc trò chuyện mới"}” cùng các tin nhắn và trích dẫn trong cuộc trò chuyện này. Tài liệu không bị xóa.`}
      label="Xóa cuộc trò chuyện" destructive onConfirm={deleteSelected} />
  </div>;
}
