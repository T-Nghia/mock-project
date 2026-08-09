"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { UploadCloud, FileText } from "lucide-react";
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

export default function UploadDocumentPage() {
  const router = useRouter();
  const { toast } = useToast();
  const [folders, setFolders] = useState<Folder[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [folderId, setFolderId] = useState("");
  const [tags, setTags] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    foldersApi.list().then(setFolders).catch(() => setFolders([]));
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Vui lòng chọn một tệp để tải lên.");
      return;
    }
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
    <div className="mx-auto max-w-xl">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <UploadCloud className="h-5 w-5" /> Tải tài liệu lên
          </CardTitle>
          <CardDescription>Hệ thống sẽ tự động trích xuất nội dung và tóm tắt sau khi tải lên.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="file">Tệp tài liệu</Label>
              <label
                htmlFor="file"
                className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed border-input bg-muted/30 px-4 py-8 text-center hover:bg-muted/50"
              >
                {file ? (
                  <>
                    <FileText className="h-6 w-6 text-primary" />
                    <span className="text-sm font-medium">{file.name}</span>
                    <span className="text-xs text-muted-foreground">{formatBytes(file.size)}</span>
                  </>
                ) : (
                  <>
                    <UploadCloud className="h-6 w-6 text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">Nhấn để chọn tệp (PDF, DOCX, PPTX...)</span>
                  </>
                )}
              </label>
              <input
                id="file"
                type="file"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="title">Tiêu đề (tuỳ chọn)</Label>
              <Input
                id="title"
                placeholder="Mặc định lấy theo tên tệp"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="folder">Thư mục (tuỳ chọn)</Label>
              <Select id="folder" value={folderId} onChange={(e) => setFolderId(e.target.value)}>
                <option value="">— Không thuộc thư mục —</option>
                {folders.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tags">Thẻ (phân tách bằng dấu phẩy)</Label>
              <Input id="tags" placeholder="vd: chương 1, ôn tập" value={tags} onChange={(e) => setTags(e.target.value)} />
            </div>

            <Button type="submit" loading={loading} className="mt-1">
              Tải lên
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
