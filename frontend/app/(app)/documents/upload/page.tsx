"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { UploadCloud, FileText, X } from "lucide-react";
import { documentsApi, foldersApi, ApiError } from "@/lib/api";
import type { Folder } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useToast } from "@/lib/toast-context";
import { formatBytes } from "@/lib/utils";

const ACCEPTED = ".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt";

export default function UploadDocumentPage() {
  const router = useRouter();
  const { toast } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [folderId, setFolderId] = useState("");
  const [tags, setTags] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    foldersApi.list().then(setFolders).catch(() => setFolders([]));
  }, []);

  function handleFile(f: File | null) {
    setFile(f);
    if (f && !title) setTitle(f.name.replace(/\.[^.]+$/, ""));
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) { setError("Vui lòng chọn một tệp để tải lên."); return; }
    setError(null);
    setLoading(true);
    try {
      const doc = await documentsApi.upload({
        file,
        title: title.trim() || undefined,
        folder_id: folderId || undefined,
        tags: tags.trim() || undefined,
      });
      toast({ title: "Tải lên thành công", description: "Hệ thống đang xử lý tài liệu.", variant: "success" });
      router.push(`/documents/${doc.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Tải lên thất bại. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg animate-fade-in">
      <Card className="overflow-hidden">
        <CardHeader className="border-b bg-muted/20">
          <CardTitle className="flex items-center gap-2">
            <UploadCloud className="h-5 w-5 text-primary" /> Tải tài liệu lên
          </CardTitle>
          <CardDescription>Hệ thống tự động trích xuất nội dung và tóm tắt sau khi tải lên.</CardDescription>
        </CardHeader>
        <CardContent className="pt-5">
          <form onSubmit={onSubmit} className="flex flex-col gap-5">
            {error && (
              <Alert variant="destructive" className="animate-slide-up">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {/* Drop zone */}
            <div className="flex flex-col gap-1.5">
              <Label>Tệp tài liệu</Label>
              <div
                onClick={() => inputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                className={`relative flex cursor-pointer flex-col items-center gap-3 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-all ${
                  dragging
                    ? "border-primary bg-primary/5 scale-[1.01]"
                    : "border-border bg-muted/20 hover:border-primary/60 hover:bg-muted/40"
                }`}
              >
                {file ? (
                  <>
                    <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10">
                      <FileText className="h-6 w-6 text-primary" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold">{file.name}</p>
                      <p className="text-xs text-muted-foreground">{formatBytes(file.size)}</p>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="absolute right-2 top-2 h-6 w-6 p-0"
                      onClick={(e) => { e.stopPropagation(); setFile(null); setTitle(""); }}
                    >
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  </>
                ) : (
                  <>
                    <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted">
                      <UploadCloud className="h-6 w-6 text-muted-foreground" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold">Kéo thả hoặc nhấn để chọn tệp</p>
                      <p className="text-xs text-muted-foreground mt-0.5">PDF, DOCX, PPTX, XLSX, TXT</p>
                    </div>
                  </>
                )}
              </div>
              <input
                ref={inputRef}
                id="file"
                type="file"
                accept={ACCEPTED}
                className="hidden"
                onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
              />
            </div>

            {/* Title */}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="title">Tiêu đề <span className="text-muted-foreground font-normal">(tuỳ chọn)</span></Label>
              <Input
                id="title"
                placeholder="Mặc định lấy theo tên tệp"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>

            {/* Folder */}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="folder">Thư mục <span className="text-muted-foreground font-normal">(tuỳ chọn)</span></Label>
              <Select id="folder" value={folderId} onChange={(e) => setFolderId(e.target.value)}>
                <option value="">— Không thuộc thư mục —</option>
                {folders.map((f) => (
                  <option key={f.id} value={f.id}>{f.name}</option>
                ))}
              </Select>
            </div>

            {/* Tags */}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tags">
                Thẻ <span className="text-muted-foreground font-normal">(phân tách bằng dấu phẩy)</span>
              </Label>
              <Input
                id="tags"
                placeholder="vd: chương 1, ôn tập, toán"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
              />
            </div>

            <Button type="submit" loading={loading} className="gradient-brand border-0 text-white hover:opacity-90">
              <UploadCloud className="h-4 w-4" /> Tải lên
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
