"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Download, FileText, Sparkles, AlertCircle } from "lucide-react";
import { documentsApi, ApiError } from "@/lib/api";
import type { DocumentMetadata } from "@/lib/types";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/documents/status-badge";
import { BookmarkButton } from "@/components/documents/bookmark-button";
import { RatingStars } from "@/components/documents/rating-stars";
import { CommentsSection } from "@/components/documents/comments-section";
import { DocumentViewer } from "@/components/documents/document-viewer";
import { DeleteDocumentButton } from "@/components/documents/delete-document-button";
import { ChatPanel } from "@/components/chat/chat-panel";
import { WorkspaceTabs } from "@/components/documents/workspace-tabs";
import { cn, formatBytes, formatDate } from "@/lib/utils";
import { useToast } from "@/lib/toast-context";

export default function DocumentDetailPage() {
  const params = useParams<{ id: string }>();
  // Reset document-specific state on navigation, never on viewport changes.
  return <DocumentWorkspace key={params.id} documentId={params.id} />;
}

function DocumentWorkspace({ documentId }: { documentId: string }) {
  const router = useRouter();
  const { toast } = useToast();
  const { user } = useAuth();
  const [doc, setDoc] = useState<DocumentMetadata | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [activePanel, setActivePanel] = useState("document");
  const [documentTab, setDocumentTab] = useState("reader");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    documentsApi.getMetadata(documentId)
      .then((metadata) => { if (!cancelled) setDoc(metadata); })
      .catch((err) => { if (!cancelled) setError(err instanceof ApiError ? err.message : "Không tải được tài liệu."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [documentId, attempt]);

  async function handleDownload() {
    setDownloading(true);
    try {
      const { blob, filename } = await documentsApi.download(documentId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast({ title: "Tải xuống thất bại", description: err instanceof ApiError ? err.message : undefined, variant: "error" });
    } finally {
      setDownloading(false);
    }
  }

  if (loading) return (
    <div role="status" className="flex h-full flex-col gap-4">
      <span className="sr-only">Đang tải tài liệu…</span>
      <Skeleton className="h-16 w-full" />
      <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[3fr_2fr]"><Skeleton /><Skeleton className="hidden xl:block" /></div>
    </div>
  );

  if (error || !doc) return (
    <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
      <AlertCircle aria-hidden="true" className="h-8 w-8 text-muted-foreground" />
      <p role="alert">{error ?? "Không tìm thấy tài liệu."}</p>
      <div className="flex gap-2">
        <Button variant="outline" onClick={() => router.back()}>Quay lại</Button>
        <Button onClick={() => setAttempt((value) => value + 1)}>Thử lại</Button>
      </div>
    </div>
  );

  const canDelete = user && (user.id === doc.uploaded_by.id || user.role === "admin");

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 sm:gap-4">
      <header className="flex shrink-0 items-center gap-3">
        <Button variant="outline" size="icon" aria-label="Quay lại" onClick={() => router.back()}><ArrowLeft aria-hidden="true" className="h-4 w-4" /></Button>
        <div className="min-w-0 flex-1">
          <p className="mb-0.5 hidden text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground sm:block">Không gian nghiên cứu</p>
          <h1 className="truncate text-base font-semibold tracking-tight sm:text-xl" title={doc.title}>{doc.title}</h1>
        </div>
        <Button size="sm" variant="outline" onClick={handleDownload} loading={downloading} aria-label="Tải xuống tài liệu">
          <Download aria-hidden="true" className="h-4 w-4" /><span className="hidden sm:inline">Tải xuống</span>
        </Button>
      </header>

      <WorkspaceTabs id="workspace" label="Không gian tài liệu" value={activePanel} onChange={setActivePanel}
        className="xl:hidden" tabs={[{ value: "document", label: "Tài liệu", icon: FileText }, { value: "assistant", label: "Trợ lý AI", icon: Sparkles }]} />

      <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section id="workspace-document-panel" role="tabpanel" aria-label="Tài liệu" className={cn("min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border border-border bg-card shadow-panel xl:flex", activePanel === "document" ? "flex" : "hidden")}>
          <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2 sm:px-4">
            <WorkspaceTabs id="document" label="Nội dung tài liệu" value={documentTab} onChange={setDocumentTab}
              tabs={[{ value: "reader", label: "Đọc tài liệu" }, { value: "details", label: "Thông tin & thảo luận" }]} />
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{doc.file_type}</span>
          </div>
          <div id="document-reader-panel" role="tabpanel" aria-labelledby="document-reader-tab" tabIndex={0} className={cn("min-h-0 flex-1 bg-muted/30 outline-none", documentTab !== "reader" && "hidden")}>
            <DocumentViewer documentId={doc.id} fileType={doc.file_type} onDownload={handleDownload} />
          </div>
          <div id="document-details-panel" role="tabpanel" aria-labelledby="document-details-tab" tabIndex={0} className={cn("min-h-0 flex-1 space-y-6 overflow-y-auto overscroll-contain p-4 outline-none sm:p-6", documentTab !== "details" && "hidden")}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <StatusBadge status={doc.processing_status} />
              <div className="flex flex-wrap gap-2">
                <BookmarkButton documentId={doc.id} />
                {canDelete && <DeleteDocumentButton documentId={doc.id} documentTitle={doc.title} onDeleted={() => { toast({ title: "Đã xóa tài liệu", variant: "success" }); router.push("/search"); }} />}
              </div>
            </div>
            <div>
              <h2 className="mb-3 text-base font-semibold">Thông tin tài liệu</h2>
              <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
                <dt className="text-muted-foreground">Người tải lên</dt><dd className="break-words">{doc.uploaded_by.full_name}</dd>
                <dt className="text-muted-foreground">Ngày tải lên</dt><dd>{formatDate(doc.created_at)}</dd>
                <dt className="text-muted-foreground">Dung lượng</dt><dd>{formatBytes(doc.file_size)}</dd>
              </dl>
            </div>
            <RatingStars documentId={doc.id} />
            {doc.tags.length > 0 && <div className="flex flex-wrap gap-1.5">{doc.tags.map((tag) => <Badge key={tag} variant="secondary" className="max-w-full whitespace-normal break-words">{tag}</Badge>)}</div>}
            <div>
              <h2 className="mb-2 text-sm font-semibold">Tóm tắt nội dung</h2>
              <p className="whitespace-pre-wrap break-words text-sm leading-7 text-muted-foreground">
                {doc.processing_status === "done" ? doc.summary || "Tài liệu chưa có bản tóm tắt." : doc.processing_status === "failed" ? "Xử lý tài liệu thất bại, không có bản tóm tắt." : "Hệ thống đang xử lý, bản tóm tắt sẽ sớm sẵn sàng."}
              </p>
            </div>
            <div className="border-t border-border pt-5"><CommentsSection documentId={doc.id} /></div>
          </div>
        </section>

        <section id="workspace-assistant-panel" role="tabpanel" aria-label="Trợ lý AI" className={cn("min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border border-border bg-card shadow-panel xl:flex", activePanel === "assistant" ? "flex" : "hidden")}>
          {doc.processing_status === "done" ? (
            <ChatPanel key={doc.id} documentId={doc.id} suggestedQuestions={doc.suggested_questions} />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-4 p-6 text-center">
              <Sparkles aria-hidden="true" className="h-8 w-8 text-muted-foreground" />
              <h2 className="font-semibold">Trợ lý AI chưa sẵn sàng</h2>
              <StatusBadge status={doc.processing_status} />
              <p className="max-w-xs text-sm leading-6 text-muted-foreground">{doc.processing_status === "failed" ? "Tài liệu chưa được xử lý thành công. Bạn vẫn có thể đọc và tải tài liệu." : "Bạn có thể đọc tài liệu trong lúc hệ thống chuẩn bị nội dung cho trợ lý AI."}</p>
              <Button variant="outline" size="sm" onClick={() => setAttempt((value) => value + 1)}>Kiểm tra lại</Button>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
