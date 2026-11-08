"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Quote, Trash2 } from "lucide-react";
import { ApiError, chatApi } from "@/lib/api";
import type { ChatSessionDetail } from "@/lib/types";
import { Button, buttonVariants } from "@/components/ui/button";
import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";
import { PageLoading, PageState } from "@/components/ui/page-state";
import { formatDate } from "@/lib/utils";

export default function ChatTranscriptPage() {
  const params = useParams<{ id: string }>();
  return <ChatTranscript key={params.id} sessionId={params.id} />;
}

function ChatTranscript({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const [session, setSession] = useState<ChatSessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    chatApi.getSession(sessionId)
      .then((result) => { if (!cancelled) setSession(result); })
      .catch((err) => { if (!cancelled) setError(err instanceof ApiError ? err.message : "Vui lòng thử lại."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [sessionId, attempt]);

  async function deleteSession() {
    await chatApi.deleteSession(sessionId);
    if (mounted.current) router.push("/chat");
  }

  return <div className="mx-auto max-w-3xl space-y-6">
    <Link href="/chat" className={buttonVariants({ variant: "outline", size: "sm" })}><ArrowLeft aria-hidden="true" className="h-4 w-4" />Lịch sử trò chuyện</Link>
    {loading ? <PageLoading label="Đang tải cuộc trò chuyện" /> : error || !session ? (
      <PageState title="Không tải được cuộc trò chuyện" description={error || "Không tìm thấy cuộc trò chuyện."} retry={() => setAttempt((value) => value + 1)} />
    ) : <>
      <header className="space-y-3">
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
          <h2 className="min-w-0 flex-1 break-words text-xl font-semibold sm:text-2xl">{session.title || "Cuộc trò chuyện mới"}</h2>
          <Button variant="outline" size="sm" onClick={() => setConfirmDelete(true)}><Trash2 aria-hidden="true" className="h-4 w-4" />Xóa cuộc trò chuyện</Button>
        </div>
        <p className="text-xs text-muted-foreground">{formatDate(session.created_at)}</p>
        {session.document_id === null ? (
          <p role="status" className="rounded-lg border border-border bg-muted/30 p-4 text-sm leading-6">Tài liệu đã bị xóa. Cuộc trò chuyện này chỉ đọc; bạn không thể gửi câu hỏi mới. Các trích dẫn là bản lưu tại thời điểm trả lời, không còn liên kết tới tài liệu gốc.</p>
        ) : <Link href={`/documents/${session.document_id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>Mở tài liệu để tiếp tục trò chuyện</Link>}
      </header>
      {session.messages.length === 0 ? <PageState title="Chưa có tin nhắn" description="Cuộc trò chuyện này chưa có nội dung." /> : (
        <section aria-label="Bản ghi cuộc trò chuyện" className="space-y-5">{session.messages.map((message) => <article key={message.id} aria-label={message.role === "user" ? "Tin nhắn của bạn" : "Câu trả lời của trợ lý AI"} className="min-w-0 rounded-xl border border-border bg-card p-4 sm:p-5">
          <p className="mb-3 text-xs font-semibold text-muted-foreground">{message.role === "user" ? "Bạn" : "Trợ lý AI"} · {formatDate(message.created_at)}</p>
          <p className="whitespace-pre-wrap break-words text-sm leading-7">{message.content}</p>
          {message.sources.length > 0 && <div className="mt-4 space-y-2">
            <p className="text-xs font-medium text-muted-foreground">Trích dẫn đã lưu · {message.sources.length}</p>
            {message.sources.map((source, index) => <details key={`${source.chunk_id}-${index}`} className="rounded-lg border border-border bg-muted/30 p-3">
              <summary className="cursor-pointer break-words text-xs font-medium leading-5"><Quote aria-hidden="true" className="mr-1 inline h-3 w-3 text-primary" />[{index + 1}] {source.heading_path.length ? source.heading_path.join(" › ") : `Đoạn trích ${index + 1}`}</summary>
              <blockquote className="mt-2 whitespace-pre-wrap break-words border-l-2 border-primary/20 pl-3 text-xs leading-6 text-muted-foreground">{source.quote}</blockquote>
            </details>)}
          </div>}
        </article>)}</section>
      )}
      <ConfirmActionDialog open={confirmDelete} onOpenChange={setConfirmDelete} title="Xóa cuộc trò chuyện?" description="Xóa vĩnh viễn cuộc trò chuyện này cùng các tin nhắn và trích dẫn. Tài liệu không bị xóa." label="Xóa cuộc trò chuyện" destructive onConfirm={deleteSession} />
    </>}
  </div>;
}
