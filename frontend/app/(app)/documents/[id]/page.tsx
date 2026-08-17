"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Download, FileText, User as UserIcon, Calendar, HardDrive, Tag, FolderOpen, Check, Copy } from "lucide-react";
import { documentsApi, ApiError } from "@/lib/api";
import type { DocumentMetadata } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/documents/status-badge";
import { formatBytes, formatDate } from "@/lib/utils";
import { useToast } from "@/lib/toast-context";

function MetaRow({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted/60">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
      </div>
      <div className="min-w-0">
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="text-sm font-medium">{value}</p>
      </div>
    </div>
  );
}

export default function DocumentDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { toast } = useToast();
  const [doc, setDoc] = useState<DocumentMetadata | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      toast({ title: "Tải xuống thành công", variant: "success" });
    } catch (err) {
      toast({ title: "Tải xuống thất bại", description: err instanceof ApiError ? err.message : undefined, variant: "error" });
    } finally {
      setDownloading(false);
    }
  }

  async function handleCopySummary() {
    if (!doc?.summary) return;
    await navigator.clipboard.writeText(doc.summary);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl flex flex-col gap-4 animate-fade-in">
        <Skeleton className="h-8 w-28 rounded-lg" />
        <Skeleton className="h-56 rounded-xl" />
        <Skeleton className="h-32 rounded-xl" />
      </div>
    );
  }

  if (error || !doc) {
    return (
      <div className="mx-auto max-w-2xl flex flex-col items-center justify-center gap-4 py-20 text-center">
        <FileText className="h-10 w-10 text-muted-foreground/40" />
        <p className="text-sm text-muted-foreground">{error ?? "Không tìm thấy tài liệu."}</p>
        <Button variant="outline" size="sm" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4" /> Quay lại
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 animate-fade-in">
      <Button variant="ghost" size="sm" className="w-fit -ml-2 text-muted-foreground hover:text-foreground" onClick={() => router.back()}>
        <ArrowLeft className="h-4 w-4" /> Quay lại
      </Button>

      {/* Main card */}
      <Card className="overflow-hidden">
        <CardHeader className="border-b bg-muted/20 pb-4">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <FileText className="h-6 w-6" />
            </div>
            <div className="flex-1 min-w-0">
              <CardTitle className="text-lg leading-tight">{doc.title}</CardTitle>
              <div className="mt-1.5 flex items-center gap-2 flex-wrap">
                <span className="text-xs uppercase font-medium text-muted-foreground tracking-wider">
                  {doc.file_type}
                </span>
                <StatusBadge status={doc.processing_status} />
              </div>
            </div>
            <Button onClick={handleDownload} loading={downloading} size="sm" className="shrink-0">
              <Download className="h-4 w-4" /> Tải xuống
            </Button>
          </div>
        </CardHeader>

        <CardContent className="flex flex-col gap-5 pt-5">
          {/* Meta grid */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <MetaRow icon={UserIcon} label="Người tải lên" value={doc.uploaded_by.full_name} />
            <MetaRow icon={Calendar} label="Ngày tạo" value={formatDate(doc.created_at)} />
            <MetaRow icon={HardDrive} label="Dung lượng" value={formatBytes(doc.file_size)} />
          </div>

          {/* Tags */}
          {doc.tags.length > 0 && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <Tag className="h-3.5 w-3.5" /> Thẻ
              </div>
              <div className="flex flex-wrap gap-1.5">
                {doc.tags.map((tag) => (
                  <Badge key={tag} variant="secondary" className="rounded-full">
                    #{tag}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Folder */}
          {doc.folder_id && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <FolderOpen className="h-4 w-4" />
              <span>Thuộc thư mục</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Summary card */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold">Tóm tắt nội dung</CardTitle>
            {doc.processing_status === "done" && doc.summary && (
              <Button variant="ghost" size="sm" onClick={handleCopySummary} className="h-7 px-2 text-xs">
                {copied ? <><Check className="h-3 w-3 text-green-600" /> Đã copy</> : <><Copy className="h-3 w-3" /> Sao chép</>}
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {doc.processing_status === "done" && doc.summary ? (
            <p className="text-sm leading-relaxed text-muted-foreground">{doc.summary}</p>
          ) : doc.processing_status === "failed" ? (
            <div className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              Xử lý tài liệu thất bại, không có bản tóm tắt.
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <div className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
              Hệ thống đang xử lý, bản tóm tắt sẽ sớm sẵn sàng...
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
