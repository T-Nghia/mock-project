"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Download, FileText, User as UserIcon, Calendar, HardDrive, Sparkles } from "lucide-react";
import { documentsApi, ApiError } from "@/lib/api";
import type { DocumentMetadata } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/documents/status-badge";
import { BookmarkButton } from "@/components/documents/bookmark-button";
import { RatingStars } from "@/components/documents/rating-stars";
import { CommentsSection } from "@/components/documents/comments-section";
import { ChatPanel } from "@/components/chat/chat-panel";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { formatBytes, formatDate } from "@/lib/utils";
import { useToast } from "@/lib/toast-context";

export default function DocumentDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { toast } = useToast();
  const [doc, setDoc] = useState<DocumentMetadata | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(false);

  useEffect(() => {
    documentsApi
      .getMetadata(params.id)
      .then(setDoc)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Không tải được tài liệu."))
      .finally(() => setLoading(false));
  }, [params.id]);

  async function handleDownload() {
    setDownloading(true);
    try {
      const { blob, filename } = await documentsApi.download(params.id);
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

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl flex flex-col gap-4">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-48" />
      </div>
    );
  }

  if (error || !doc) {
    return (
      <div className="mx-auto max-w-2xl text-center">
        <p className="text-sm text-muted-foreground">{error ?? "Không tìm thấy tài liệu."}</p>
        <Button variant="outline" className="mt-4" onClick={() => router.back()}>
          Quay lại
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <Button variant="ghost" size="sm" className="w-fit" onClick={() => router.back()}>
        <ArrowLeft className="h-4 w-4" /> Quay lại
      </Button>

      <Card>
        <CardHeader className="flex-row items-start justify-between space-y-0">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FileText className="h-5 w-5" />
            </div>
            <div>
              <CardTitle className="text-lg">{doc.title}</CardTitle>
              <p className="mt-1 text-xs uppercase text-muted-foreground">{doc.file_type}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <BookmarkButton documentId={doc.id} />
            <Button onClick={handleDownload} loading={downloading} size="sm">
              <Download className="h-4 w-4" /> Tải xuống
            </Button>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <UserIcon className="h-4 w-4" /> {doc.uploaded_by.full_name}
            </div>
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Calendar className="h-4 w-4" /> {formatDate(doc.created_at)}
            </div>
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <HardDrive className="h-4 w-4" /> {formatBytes(doc.file_size)}
            </div>
            <StatusBadge status={doc.processing_status} />
          </div>

          <RatingStars documentId={doc.id} />

          {doc.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {doc.tags.map((tag) => (
                <Badge key={tag} variant="secondary">
                  {tag}
                </Badge>
              ))}
            </div>
          )}

          <div>
            <h3 className="mb-1.5 text-sm font-medium">Tóm tắt nội dung</h3>
            {doc.processing_status === "done" && doc.summary ? (
              <p className="text-sm leading-relaxed text-muted-foreground">{doc.summary}</p>
            ) : doc.processing_status === "failed" ? (
              <p className="text-sm text-destructive">Xử lý tài liệu thất bại, không có bản tóm tắt.</p>
            ) : (
              <p className="text-sm text-muted-foreground">Hệ thống đang xử lý, bản tóm tắt sẽ sớm sẵn sàng.</p>
            )}
          </div>

          {doc.processing_status === "done" && (
            <div className="rounded-lg border border-primary/20 bg-primary/5 p-4">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 text-sm font-medium text-primary">
                  <Sparkles className="h-4 w-4" /> Trợ lý AI
                </div>
                <Button size="sm" onClick={() => setChatOpen(true)}>
                  Trò chuyện với tài liệu
                </Button>
              </div>
              {doc.suggested_questions.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {doc.suggested_questions.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => setChatOpen(true)}
                      className="rounded-full border border-primary/30 bg-background px-3 py-1 text-xs text-foreground transition-colors hover:bg-primary/10"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">Hỏi trợ lý AI bất cứ điều gì về nội dung tài liệu.</p>
              )}
            </div>
          )}

          <div className="border-t border-border pt-5">
            <CommentsSection documentId={doc.id} />
          </div>
        </CardContent>
      </Card>

      <Dialog open={chatOpen} onOpenChange={setChatOpen}>
        <DialogContent className="max-w-lg" onClose={() => setChatOpen(false)}>
          <DialogHeader>
            <DialogTitle>Trò chuyện với tài liệu</DialogTitle>
            <DialogDescription className="truncate">{doc.title}</DialogDescription>
          </DialogHeader>
          {chatOpen && <ChatPanel documentId={doc.id} suggestedQuestions={doc.suggested_questions} />}
        </DialogContent>
      </Dialog>
    </div>
  );
}
