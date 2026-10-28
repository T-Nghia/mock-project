"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, CheckCircle2, FileText, Loader2, UploadCloud, X } from "lucide-react";
import { documentsApi, ApiError } from "@/lib/api";
import type { DocumentResponse } from "@/lib/types";
import { useAuth } from "@/lib/auth-context";
import { Card } from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { StatusBadge } from "@/components/documents/status-badge";
import { useOwnedFolders } from "@/components/documents/use-owned-folders";
import { UPLOAD_EXTENSIONS, validateUploadFile, validateUploadMetadata } from "@/components/documents/upload-validation";
import { cn, formatBytes } from "@/lib/utils";

export default function UploadDocumentPage() {
  const { user } = useAuth();
  const owned = useOwnedFolders(user?.role === "teacher" ? user.id : undefined);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [folderId, setFolderId] = useState("");
  const [tags, setTags] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [metadataErrors, setMetadataErrors] = useState<{ title: string | null; tags: string | null }>({ title: null, tags: null });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [validating, setValidating] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [uploaded, setUploaded] = useState<DocumentResponse | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const chooseRef = useRef<HTMLButtonElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const submitLock = useRef(false);
  const validationId = useRef(0);
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { if (uploaded) resultRef.current?.focus(); }, [uploaded]);

  async function chooseFile(files: FileList | File[] | null) {
    if (submitLock.current || !files?.length) return;
    const id = ++validationId.current;
    if (files.length !== 1) { setFileError("Chỉ chọn một tệp cho mỗi lần tải lên."); setValidating(false); return; }
    setValidating(true);
    setError(null);
    try {
      const selected = files[0];
      const problem = await validateUploadFile(selected);
      if (id !== validationId.current || !mounted.current) return;
      setFileError(problem);
      if (!problem) { setFile(selected); setMetadataErrors({ title: null, tags: null }); }
    } catch {
      if (id === validationId.current && mounted.current) setFileError("Không đọc được tệp. Vui lòng chọn lại.");
    } finally {
      if (id === validationId.current && mounted.current) setValidating(false);
    }
  }

  function removeFile() {
    if (submitLock.current) return;
    validationId.current++;
    setFile(null); setFileError(null); setValidating(false);
    if (inputRef.current) inputRef.current.value = "";
    chooseRef.current?.focus();
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (submitLock.current || validating || (user?.role !== "teacher" && user?.role !== "admin")) return;
    if (!file) { setFileError("Vui lòng chọn một tệp để tải lên."); chooseRef.current?.focus(); return; }
    if (fileError) { chooseRef.current?.focus(); return; }
    const errors = validateUploadMetadata(title, file.name, tags);
    setMetadataErrors(errors);
    if (errors.title || errors.tags) { document.getElementById(errors.title ? "upload-title" : "upload-tags")?.focus(); return; }
    if (folderId && !owned.folders.some((item) => item.id === folderId)) { setError("Thư mục đã chọn không còn khả dụng. Hãy chọn lại thư mục."); return; }
    submitLock.current = true;
    setError(null);
    setLoading(true);
    try {
      const doc = await documentsApi.upload({ file, title: title.trim() || undefined,
        folder_id: user.role === "teacher" ? folderId || undefined : undefined, tags: tags.trim() || undefined });
      if (mounted.current) setUploaded(doc);
      // Keep the lock after success; only an explicit new upload clears it.
    } catch (err) {
      submitLock.current = false;
      if (mounted.current) setError(err instanceof ApiError ? err.message : "Không xác nhận được kết quả tải lên. Hãy kiểm tra thư viện trước khi gửi lại để tránh tạo tài liệu trùng.");
    } finally {
      if (mounted.current) setLoading(false);
    }
  }

  if (!user || (user.role !== "teacher" && user.role !== "admin")) return null;

  if (uploaded) return <div ref={resultRef} tabIndex={-1} className="mx-auto max-w-2xl outline-none"><Card className="flex flex-col items-center gap-5 p-6 text-center sm:p-10"><span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-success/10 text-success"><CheckCircle2 aria-hidden="true" className="h-7 w-7" /></span><div role="status"><h2 className="text-2xl font-semibold tracking-tight">Đã tải tài liệu lên</h2><p className="mt-3 break-words text-sm font-medium">{uploaded.title}</p></div><div className="flex flex-wrap items-center justify-center gap-2 text-sm text-muted-foreground"><span>Trạng thái xử lý:</span><StatusBadge status={uploaded.processing_status} /></div><p className="max-w-md text-sm leading-7 text-muted-foreground">Tệp đã được lưu. Trích xuất nội dung, chia đoạn và tạo dữ liệu cho trợ lý AI là bước xử lý riêng. Mở tài liệu để xem trạng thái hiện tại.</p><div className="flex flex-wrap justify-center gap-3"><Link href={`/documents/${uploaded.id}`} className={buttonVariants()}>Mở tài liệu<ArrowRight aria-hidden="true" className="h-4 w-4" /></Link><Button variant="outline" onClick={() => { setUploaded(null); setFile(null); setTitle(""); setTags(""); setFolderId(""); setError(null); setFileError(null); setMetadataErrors({ title: null, tags: null }); submitLock.current = false; }}>Tải tài liệu khác</Button></div><Link href="/search" className="text-sm text-primary underline-offset-4 hover:underline">Về thư viện tài liệu</Link></Card></div>;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header><Link href="/search" className="mb-4 inline-flex items-center gap-2 rounded text-xs text-muted-foreground hover:text-primary"><ArrowLeft aria-hidden="true" className="h-3.5 w-3.5" />Thư viện tài liệu</Link><h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Tải tài liệu lên</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">Thêm tài nguyên vào thư viện, sẵn sàng cho việc đọc và học cùng AI.</p></header>
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card className="p-4 sm:p-6"><form aria-label="Tải tài liệu" onSubmit={onSubmit} noValidate className="space-y-6">
          <div><h3 className="mb-3 flex items-center gap-2 text-sm font-semibold"><span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-xs">1</span>Chọn tài liệu</h3>
            <div data-testid="upload-dropzone" onDragOver={(event) => { event.preventDefault(); if (!loading) setDragging(true); }} onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }} onDrop={(event) => { event.preventDefault(); setDragging(false); void chooseFile(event.dataTransfer.files); }} className={cn("rounded-xl border-2 border-dashed px-4 py-7 text-center transition-colors", dragging ? "border-primary bg-primary/5" : "border-border bg-background", loading && "opacity-60")}>
              <UploadCloud aria-hidden="true" className="mx-auto mb-3 h-8 w-8 text-primary" strokeWidth={1.5} /><p className="text-sm font-medium">Kéo thả tài liệu vào đây</p><p className="mb-4 mt-1 text-xs text-muted-foreground">hoặc chọn một tệp từ thiết bị của bạn</p>
              <input ref={inputRef} id="upload-file" type="file" tabIndex={-1} className="sr-only" aria-label="Tệp tài liệu" accept={UPLOAD_EXTENSIONS.map((ext) => `.${ext}`).join(",")} disabled={loading} onChange={(event) => { void chooseFile(event.target.files); event.target.value = ""; }} />
              <Button ref={chooseRef} type="button" variant="outline" disabled={loading} aria-describedby="upload-file-help upload-file-error" onClick={() => inputRef.current?.click()}>{file ? "Thay đổi tệp" : "Chọn tệp"}</Button>
              <p id="upload-file-help" className="mt-4 text-xs leading-5 text-muted-foreground">PDF, DOC, DOCX, TXT, PPTX, JPG, JPEG, PNG<br />Tối đa 50 MiB · Một tệp mỗi lần</p>
            </div>
            {validating && <p role="status" className="mt-3 flex items-center gap-2 text-xs text-muted-foreground"><Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />Đang kiểm tra tệp…</p>}
            {file && <div className="mt-3 flex min-w-0 items-center gap-3 rounded-lg border border-border p-3"><FileText aria-hidden="true" className="h-5 w-5 shrink-0 text-primary" /><div className="min-w-0 flex-1"><p className="break-words text-sm font-medium">{file.name}</p><p className="mt-1 text-xs text-muted-foreground">{formatBytes(file.size)}</p></div><Button type="button" size="icon" variant="ghost" aria-label="Bỏ tệp" disabled={loading} onClick={removeFile}><X aria-hidden="true" className="h-4 w-4" /></Button></div>}
            <div id="upload-file-error">{fileError && <p role="alert" className="mt-3 text-sm leading-6 text-destructive">{fileError}{file ? " Tệp đã chọn trước đó vẫn được giữ; hãy chọn lại hoặc bỏ tệp." : ""}</p>}</div>
          </div>
          <fieldset disabled={loading} className="min-w-0 space-y-4 border-t border-border pt-5"><legend className="sr-only">Thông tin tài liệu</legend><h3 className="flex items-center gap-2 text-sm font-semibold"><span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-xs">2</span>Thông tin tài liệu</h3>
            <div className="space-y-2"><Label htmlFor="upload-title">Tiêu đề <span className="font-normal text-muted-foreground">(tùy chọn)</span></Label><Input id="upload-title" placeholder="Để trống để dùng tên tệp" value={title} onChange={(event) => { setTitle(event.target.value); setMetadataErrors((previous) => ({ ...previous, title: null })); }} aria-invalid={!!metadataErrors.title} aria-describedby="upload-title-help" /><p id="upload-title-help" role={metadataErrors.title ? "alert" : undefined} className={cn("text-xs leading-5", metadataErrors.title ? "text-destructive" : "text-muted-foreground")}>{metadataErrors.title || "Tối đa 500 ký tự. Chọn tên dễ tìm và dễ nhận biết."}</p></div>
            {user.role === "teacher" && <div className="space-y-2"><Label htmlFor="upload-folder">Thư mục <span className="font-normal text-muted-foreground">(tùy chọn)</span></Label><Select id="upload-folder" value={folderId} onChange={(event) => setFolderId(event.target.value)} disabled={loading || owned.loading || owned.error}><option value="">Không thuộc thư mục</option>{owned.folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</Select>{owned.loading && <p role="status" className="text-xs text-muted-foreground">Đang tải thư mục…</p>}{owned.error && <div><p role="alert" className="text-xs leading-5 text-destructive">Không tải được thư mục. Bạn vẫn có thể tải tài liệu không thuộc thư mục.</p><Button type="button" variant="ghost" size="sm" onClick={owned.retry}>Thử lại thư mục</Button></div>}</div>}
            <div className="space-y-2"><Label htmlFor="upload-tags">Thẻ <span className="font-normal text-muted-foreground">(tùy chọn)</span></Label><Input id="upload-tags" placeholder="Ví dụ: học máy, chương 1, ôn tập" value={tags} onChange={(event) => { setTags(event.target.value); setMetadataErrors((previous) => ({ ...previous, tags: null })); }} aria-invalid={!!metadataErrors.tags} aria-describedby="upload-tags-help" /><p id="upload-tags-help" role={metadataErrors.tags ? "alert" : undefined} className={cn("text-xs leading-5", metadataErrors.tags ? "text-destructive" : "text-muted-foreground")}>{metadataErrors.tags || "Phân tách bằng dấu phẩy. Mỗi thẻ tối đa 100 ký tự."}</p></div>
          </fieldset>
          {error && <div role="alert" className="rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-sm leading-6 text-destructive"><p className="font-semibold">Tải lên chưa thành công</p><p className="mt-1 break-words">{error}</p><p className="mt-2 text-xs">Tệp và thông tin đã nhập vẫn được giữ nguyên.</p></div>}
          <div className="space-y-3 border-t border-border pt-5"><Button type="submit" loading={loading} disabled={validating} className="w-full"><UploadCloud aria-hidden="true" className="h-4 w-4" />{loading ? "Đang gửi tài liệu…" : error ? "Thử tải lên lại" : "Tải lên"}</Button>{loading && <p role="status" className="text-center text-xs leading-5 text-muted-foreground">Đang gửi tệp. Vui lòng giữ trang này mở đến khi có kết quả.</p>}<p className="text-center text-xs leading-5 text-muted-foreground">Tải lên thành công không đồng nghĩa với xử lý AI hoàn tất.</p></div>
        </form></Card>
        <aside aria-label="Hướng dẫn tải tài liệu" className="space-y-4"><Card className="p-5"><h3 className="text-sm font-semibold">Từ tài liệu đến kiến thức</h3><ol className="mt-5 space-y-5">{[{ title: "Tải tệp lên", description: "Tệp và thông tin được gửi đến hệ thống." }, { title: "Xử lý nội dung", description: "Hệ thống trích xuất và chuẩn bị tài liệu cho trợ lý AI." }, { title: "Đọc và khám phá", description: "Mở tài liệu để đọc, xem trạng thái và đặt câu hỏi khi đã sẵn sàng." }].map((step, index) => <li key={step.title} className="flex gap-3"><span aria-hidden="true" className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/5 text-xs font-medium text-primary">{index + 1}</span><div><p className="text-sm font-medium">{step.title}</p><p className="mt-1 text-xs leading-6 text-muted-foreground">{step.description}</p></div></li>)}</ol></Card><p className="px-1 text-xs leading-6 text-muted-foreground">Dùng tệp gốc với nội dung rõ ràng. Thời gian xử lý phụ thuộc vào tài liệu; bạn có thể kiểm tra trạng thái trong trang tài liệu.</p></aside>
      </div>
    </div>
  );
}
