"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, ArrowUpRight, ChevronLeft, ChevronRight, FileText, Folder, Library, Search, UploadCloud, X } from "lucide-react";
import { searchApi } from "@/lib/api";
import type { DocumentSearchResult, SearchPaginatedResponse } from "@/lib/types";
import { useAuth } from "@/lib/auth-context";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useOwnedFolders } from "@/components/documents/use-owned-folders";
import { formatDate } from "@/lib/utils";

const PAGE_SIZE = 10;

function ResultsLoading() {
  return <div role="status" aria-label="Đang tải tài liệu" className="space-y-3"><span className="sr-only">Đang tải tài liệu…</span>{[0, 1, 2].map((item) => <Skeleton key={item} className="h-40 rounded-xl" />)}</div>;
}

export default function SearchPage() {
  return <Suspense fallback={<ResultsLoading />}><DocumentLibrary /></Suspense>;
}

function DocumentLibrary() {
  const router = useRouter();
  const params = useSearchParams();
  const { user } = useAuth();
  const owned = useOwnedFolders(user?.role === "teacher" ? user.id : undefined);
  const activeKeyword = params.get("keyword")?.trim() || "";
  const activeSubject = params.get("subject")?.trim() || "";
  const activeTags = params.getAll("tags").map((tag) => tag.trim()).filter(Boolean).join(", ");
  const rawFolder = params.get("folder_id") || "";
  const activeFolder = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(rawFolder) ? rawFolder : "";
  const rawPage = Number(params.get("page") || 1);
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1;
  const queryKey = JSON.stringify([activeKeyword, activeSubject, activeTags, activeFolder, page]);
  const [keyword, setKeyword] = useState(activeKeyword);
  const [subject, setSubject] = useState(activeSubject);
  const [tags, setTags] = useState(activeTags);
  const [folder, setFolder] = useState(activeFolder);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ key: string; result: SearchPaginatedResponse | null; error: boolean }>({ key: "", result: null, error: false });
  const searchRef = useRef<HTMLInputElement>(null);
  const lastNavigation = useRef<string | null>(null);

  useEffect(() => {
    setKeyword(activeKeyword);
    setSubject(activeSubject);
    setTags(activeTags);
    setFolder(activeFolder);
    lastNavigation.current = null;
  }, [activeKeyword, activeSubject, activeTags, activeFolder, page]);

  useEffect(() => {
    let cancelled = false;
    setState({ key: queryKey, result: null, error: false });
    searchApi.search({ keyword: activeKeyword || undefined, subject: activeSubject || undefined,
      tags: activeTags ? activeTags.split(",").map((tag) => tag.trim()).filter(Boolean) : undefined,
      folder_id: activeFolder || undefined, page, page_size: PAGE_SIZE })
      .then((result) => { if (!cancelled) setState({ key: queryKey, result, error: false }); })
      .catch(() => { if (!cancelled) setState({ key: queryKey, result: null, error: true }); });
    return () => { cancelled = true; };
  }, [queryKey, activeKeyword, activeSubject, activeTags, activeFolder, page, attempt]);

  const result = state.key === queryKey ? state.result : null;
  const error = state.key === queryKey && state.error;
  const loading = !result && !error;
  const hasFilters = !!(activeKeyword || activeSubject || activeTags || activeFolder);
  const canUpload = user?.role === "teacher" || user?.role === "admin";
  const dirty = keyword.trim() !== activeKeyword || subject.trim() !== activeSubject || tags.trim() !== activeTags || folder !== activeFolder;

  function navigate(next: { keyword: string; subject: string; tags: string; folder: string; page: number }) {
    const query = new URLSearchParams();
    if (next.keyword.trim()) query.set("keyword", next.keyword.trim());
    if (next.subject.trim()) query.set("subject", next.subject.trim());
    next.tags.split(",").map((tag) => tag.trim()).filter(Boolean).forEach((tag) => query.append("tags", tag));
    if (next.folder) query.set("folder_id", next.folder);
    if (next.page > 1) query.set("page", String(next.page));
    const href = "/search" + (query.size ? "?" + query.toString() : "");
    if (lastNavigation.current === href) return;
    lastNavigation.current = href;
    router.push(href, { scroll: false });
  }
  function goPage(nextPage: number) {
    navigate({ keyword: activeKeyword, subject: activeSubject, tags: activeTags, folder: activeFolder, page: nextPage });
  }
  function resetFilters() {
    setKeyword(""); setSubject(""); setTags(""); setFolder("");
    navigate({ keyword: "", subject: "", tags: "", folder: "", page: 1 });
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0"><p className="mb-2 text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">Khám phá & học tập</p><h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Thư viện tài liệu</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">Tìm tài nguyên phù hợp và mở ra những góc nhìn mới.</p></div>
        {canUpload && <Link href="/documents/upload" className={buttonVariants({ className: "w-fit" })}><UploadCloud aria-hidden="true" className="h-4 w-4" />Tải tài liệu lên</Link>}
      </header>

      <Card className="p-4 sm:p-5">
        <form role="search" aria-label="Tìm kiếm thư viện" onSubmit={(event) => { event.preventDefault(); navigate({ keyword, subject, tags, folder, page: 1 }); }} className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="min-w-0 flex-1"><Label htmlFor="library-keyword">Tìm kiếm tài liệu</Label><div className="relative mt-2"><Search aria-hidden="true" className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" /><Input ref={searchRef} id="library-keyword" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="Nhập tiêu đề, thẻ hoặc môn học…" className="pl-10 pr-11" />{keyword && <button type="button" aria-label="Xóa từ khóa" className="absolute right-1 top-1 flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent" onClick={() => { setKeyword(""); navigate({ keyword: "", subject: activeSubject, tags: activeTags, folder: activeFolder, page: 1 }); searchRef.current?.focus(); }}><X aria-hidden="true" className="h-4 w-4" /></button>}</div></div>
            <Button type="submit"><Search aria-hidden="true" className="h-4 w-4" />Tìm kiếm</Button>
          </div>
          <div className="grid gap-3 border-t border-border pt-4 sm:grid-cols-2 xl:grid-cols-3">
            <div className="space-y-2"><Label htmlFor="library-subject">Môn học</Label><Input id="library-subject" value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="Nhập tên môn học" /></div>
            <div className="space-y-2"><Label htmlFor="library-tags">Thẻ</Label><Input id="library-tags" value={tags} onChange={(event) => setTags(event.target.value)} placeholder="Ví dụ: ôn tập, học máy" aria-describedby="library-filter-help" /></div>
            {user?.role === "teacher" && <div className="space-y-2"><Label htmlFor="library-folder">Thư mục của bạn</Label><Select id="library-folder" value={folder} onChange={(event) => setFolder(event.target.value)} disabled={owned.loading || owned.error}><option value="">Tất cả thư mục</option>{folder && !owned.folders.some((item) => item.id === folder) && <option value={folder}>Thư mục từ liên kết</option>}{owned.folders.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select>{owned.loading && <p role="status" className="text-xs text-muted-foreground">Đang tải thư mục…</p>}{owned.error && <div className="text-xs text-destructive"><p role="alert">Không tải được danh sách thư mục.</p><Button type="button" size="sm" variant="ghost" onClick={owned.retry}>Thử lại thư mục</Button></div>}</div>}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2"><p id="library-filter-help" className="text-xs leading-5 text-muted-foreground">Thẻ cách nhau bằng dấu phẩy; tìm tài liệu có ít nhất một thẻ phù hợp. Nhấn Tìm kiếm để áp dụng.</p>{(hasFilters || dirty) && <Button type="button" variant="ghost" size="sm" onClick={resetFilters}>Xóa bộ lọc</Button>}</div>
          {dirty && <p className="text-xs text-primary">Có thay đổi chưa áp dụng.</p>}
        </form>
      </Card>

      <section aria-label="Kết quả tài liệu" aria-busy={loading} className="min-w-0 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2"><p role="status" className="text-sm font-medium">{loading ? "Đang tìm tài liệu…" : error ? "Chưa tải được kết quả" : result!.items.length === 0 && page > 1 ? "Không có tài liệu trên trang này" : `${result!.total.toLocaleString("vi-VN")} tài liệu${hasFilters ? " phù hợp" : " trong thư viện"}`}</p><span className="text-xs text-muted-foreground">Mới nhất trước</span></div>
        {hasFilters && <div className="flex flex-wrap gap-2" aria-label="Điều kiện đang áp dụng">{[activeKeyword && `Từ khóa: ${activeKeyword}`, activeSubject && `Môn học: ${activeSubject}`, activeTags && `Thẻ: ${activeTags}`, activeFolder && `Thư mục: ${owned.folders.find((item) => item.id === activeFolder)?.name || activeFolder}`].filter(Boolean).map((text) => <Badge key={String(text)} variant="secondary" className="max-w-full whitespace-normal break-words">{text}</Badge>)}</div>}
        {loading ? <ResultsLoading /> : error ? <Card className="flex min-h-72 flex-col items-center justify-center gap-4 p-6 text-center"><AlertCircle aria-hidden="true" className="h-8 w-8 text-destructive" /><div role="alert"><h3 className="font-semibold">Không tải được thư viện</h3><p className="mt-2 text-sm text-muted-foreground">Vui lòng thử lại. Các điều kiện tìm kiếm của bạn được giữ nguyên.</p></div><Button variant="outline" onClick={() => setAttempt((value) => value + 1)}>Thử lại</Button></Card>
          : result!.items.length === 0 ? <Card className="flex min-h-72 flex-col items-center justify-center gap-4 p-6 text-center"><Library aria-hidden="true" className="h-9 w-9 text-muted-foreground" /><div><h3 className="font-semibold">{page > 1 ? "Trang này không còn kết quả" : hasFilters ? "Không tìm thấy tài liệu phù hợp" : "Thư viện chưa có tài liệu"}</h3><p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">{page > 1 ? "Hãy quay về trang đầu để cập nhật kết quả." : hasFilters ? "Thử một từ khóa khác hoặc bỏ bớt điều kiện tìm kiếm." : "Tài liệu được tải lên sẽ xuất hiện tại đây."}</p></div>{page > 1 ? <Button variant="outline" onClick={() => goPage(1)}>Về trang đầu</Button> : hasFilters ? <Button variant="outline" onClick={resetFilters}>Xóa bộ lọc</Button> : canUpload ? <Link href="/documents/upload" className={buttonVariants()}>Tải tài liệu đầu tiên</Link> : null}</Card>
          : <><ul className="space-y-3">{result!.items.map((doc) => <li key={doc.id}><ResultCard doc={doc} /></li>)}</ul><nav aria-label="Phân trang tài liệu" className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4"><p className="text-xs leading-5 text-muted-foreground">Trang {result!.page}/{result!.total_pages} · {result!.total.toLocaleString("vi-VN")} kết quả</p><div className="flex gap-2"><Button variant="outline" size="sm" disabled={result!.page <= 1} onClick={() => goPage(result!.page - 1)}><ChevronLeft aria-hidden="true" className="h-4 w-4" />Trước</Button><Button variant="outline" size="sm" disabled={result!.page >= result!.total_pages} onClick={() => goPage(result!.page + 1)}>Tiếp theo<ChevronRight aria-hidden="true" className="h-4 w-4" /></Button></div></nav></>}
      </section>
    </div>
  );
}

function ResultCard({ doc }: { doc: DocumentSearchResult }) {
  return <Link href={`/documents/${doc.id}`} className="group block rounded-xl border border-border bg-card p-4 shadow-sm transition-colors hover:border-primary/40 sm:p-5">
    <div className="flex items-start gap-3 sm:gap-4"><span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-primary/10 bg-primary/5 text-primary"><FileText aria-hidden="true" className="h-5 w-5" /></span><div className="min-w-0 flex-1"><div className="flex items-start gap-3"><h3 className="min-w-0 flex-1 break-words text-base font-semibold leading-6 tracking-tight group-hover:text-primary">{doc.title}</h3><ArrowUpRight aria-hidden="true" className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" /></div><div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground"><span className="font-medium uppercase text-primary">{doc.file_type}</span><time dateTime={doc.created_at}>{formatDate(doc.created_at)}</time>{doc.folder_name && <span className="flex min-w-0 items-start gap-1"><Folder aria-hidden="true" className="h-3.5 w-3.5 shrink-0" /><span className="break-words">{doc.folder_name}</span></span>}</div>{doc.summary && <p className="mt-3 line-clamp-2 break-words text-sm leading-6 text-muted-foreground">{doc.summary}</p>}{(doc.subject || doc.tags.length > 0) && <div className="mt-3 flex flex-wrap gap-1.5">{doc.subject && <Badge variant="secondary" className="max-w-full whitespace-normal break-words">{doc.subject}</Badge>}{doc.tags.map((tag, index) => <Badge key={`${tag}-${index}`} variant="outline" className="max-w-full whitespace-normal break-words">#{tag}</Badge>)}</div>}</div></div>
  </Link>;
}
