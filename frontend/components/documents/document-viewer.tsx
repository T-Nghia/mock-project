"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Download, Loader2 } from "lucide-react";
import { documentsApi, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";

const VIEWABLE_INLINE = new Set(["pdf", "jpg", "jpeg", "png", "txt"]);

interface DocumentViewerProps {
  documentId: string;
  fileType: string;
  onDownload: () => void;
}

export function DocumentViewer({ documentId, fileType, onDownload }: DocumentViewerProps) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [textContent, setTextContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const ext = fileType.toLowerCase().replace(/^\./, "");
  const canView = VIEWABLE_INLINE.has(ext);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setObjectUrl(null);
    setTextContent(null);
    if (!canView) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    let createdUrl: string | null = null;

    documentsApi
      .view(documentId)
      .then(async ({ blob }) => {
        if (cancelled) return;
        if (ext === "txt") {
          const text = await blob.text();
          if (!cancelled) setTextContent(text);
        } else {
          createdUrl = URL.createObjectURL(blob);
          if (!cancelled) setObjectUrl(createdUrl);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Không thể tải tài liệu để xem.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [documentId, ext, canView, attempt]);

  if (!canView) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <div className="flex h-11 w-11 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <AlertTriangle className="h-5 w-5" />
        </div>
        <p className="max-w-xs text-sm text-muted-foreground">
          Định dạng .{ext} chưa hỗ trợ xem trực tiếp trên trình duyệt. Vui lòng tải xuống để xem.
        </p>
        <Button size="sm" onClick={onDownload}>
          <Download className="h-4 w-4" /> Tải xuống
        </Button>
      </div>
    );
  }

  if (loading) {
    return (
      <div role="status" className="flex h-full items-center justify-center gap-2 p-6 text-muted-foreground">
        <Loader2 aria-hidden="true" className="h-5 w-5 animate-spin" /> Đang tải nội dung…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <p role="alert" className="text-sm text-destructive">{error}</p>
        <Button size="sm" onClick={() => setAttempt((value) => value + 1)}>Thử tải lại</Button>
        <Button size="sm" variant="outline" onClick={onDownload}>
          <Download className="h-4 w-4" /> Tải xuống thay thế
        </Button>
      </div>
    );
  }

  if (ext === "txt" && textContent !== null) {
    return (
      <div className="h-full overflow-y-auto overscroll-contain p-4 sm:p-6">
        <pre className="mx-auto min-h-full max-w-3xl whitespace-pre-wrap break-words rounded-lg border border-border bg-card p-5 font-sans text-sm leading-7 shadow-sm sm:p-8">{textContent}</pre>
      </div>
    );
  }

  if (ext === "pdf" && objectUrl) {
    return (
      <iframe
        src={objectUrl}
        title="Xem tài liệu PDF"
        className="block h-full w-full border-0 bg-muted"
      />
    );
  }

  if ((ext === "jpg" || ext === "jpeg" || ext === "png") && objectUrl) {
    return (
      <div className="flex h-full items-start justify-center overflow-y-auto overscroll-contain p-4">
        {/* Authenticated blob URLs are managed and revoked by this viewer. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={objectUrl} alt="Xem trước tài liệu" className="h-auto max-w-full rounded-md" />
      </div>
    );
  }

  return null;
}
