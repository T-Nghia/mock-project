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

  const ext = fileType.toLowerCase().replace(/^\./, "");
  const canView = VIEWABLE_INLINE.has(ext);

  useEffect(() => {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId, ext, canView]);

  if (!canView) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border py-14 text-center">
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
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border py-14 text-center">
        <p className="text-sm text-destructive">{error}</p>
        <Button size="sm" variant="outline" onClick={onDownload}>
          <Download className="h-4 w-4" /> Tải xuống thay thế
        </Button>
      </div>
    );
  }

  if (ext === "txt" && textContent !== null) {
    return (
      <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-muted/30 p-4 text-sm leading-relaxed">
        {textContent}
      </pre>
    );
  }

  if (ext === "pdf" && objectUrl) {
    return (
      <iframe
        src={objectUrl}
        title="Xem tài liệu PDF"
        className="h-[75vh] w-full rounded-lg border border-border"
      />
    );
  }

  if ((ext === "jpg" || ext === "jpeg" || ext === "png") && objectUrl) {
    // eslint-disable-next-line @next/next/no-img-element
    return (
      <div className="flex justify-center rounded-lg border border-border bg-muted/30 p-3">
        <img src={objectUrl} alt="Xem trước tài liệu" className="max-h-[70vh] w-auto rounded-md object-contain" />
      </div>
    );
  }

  return null;
}
