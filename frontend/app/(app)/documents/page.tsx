"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { FileText, Search, X, Clock } from "lucide-react";
import { searchApi, ApiError } from "@/lib/api";
import type { DocumentSearchResult, SearchPaginatedResponse } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

import { formatDate } from "@/lib/utils";
import { useToast } from "@/lib/toast-context";

const PAGE_SIZE = 15;

function FileTypeIcon({ type }: { type: string }) {
  const lower = type.toLowerCase();
  if (lower.includes("pdf")) return <span className="text-[10px] font-bold text-red-500">PDF</span>;
  if (lower.includes("word") || lower.includes("doc")) return <span className="text-[10px] font-bold text-blue-600">DOC</span>;
  if (lower.includes("sheet") || lower.includes("excel") || lower.includes("xlsx")) return <span className="text-[10px] font-bold text-green-600">XLS</span>;
  if (lower.includes("ppt") || lower.includes("presentation")) return <span className="text-[10px] font-bold text-orange-500">PPT</span>;
  return <span className="text-[10px] font-bold text-muted-foreground">FILE</span>;
}

export default function DocumentsPage() {
  const { toast } = useToast();
  const [keyword, setKeyword] = useState("");
  const [inputValue, setInputValue] = useState("");
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<SearchPaginatedResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(
    async (kw: string, p: number) => {
      setLoading(true);
      try {
        const data = await searchApi.search({
          keyword: kw || undefined,
          page: p,
          page_size: PAGE_SIZE,
        });
        setResult(data);
      } catch (err) {
        toast({
          title: "Không tải được danh sách tài liệu",
          description: err instanceof ApiError ? err.message : undefined,
          variant: "error",
        });
      } finally {
        setLoading(false);
      }
    },
    [toast]
  );

  useEffect(() => {
    load("", 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onSearch(e: React.FormEvent) {
    e.preventDefault();
    setKeyword(inputValue);
    setPage(1);
    load(inputValue, 1);
  }

  function clearSearch() {
    setInputValue("");
    setKeyword("");
    setPage(1);
    load("", 1);
  }

  function goPage(p: number) {
    setPage(p);
    load(keyword, p);
  }

  return (
    <div className="flex flex-col gap-5 animate-fade-in">
      {/* Header + Search */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-tight">Tài liệu</h2>
          <p className="text-sm text-muted-foreground">
            {result ? `${result.total} tài liệu` : "Đang tải..."}
          </p>
        </div>

        <form onSubmit={onSearch} className="flex gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Tìm kiếm tài liệu..."
              className="pl-9 w-60"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
            />
            {inputValue && (
              <button
                type="button"
                onClick={clearSearch}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <Button type="submit" size="sm">Tìm</Button>
        </form>
      </div>

      {/* Results */}
      {loading ? (
        <div className="flex flex-col gap-3">
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-20 rounded-xl" />
          ))}
        </div>
      ) : !result || result.items.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border bg-card py-20 text-center shadow-sm">
          <FileText className="mb-3 h-10 w-10 text-muted-foreground/40" />
          <p className="text-sm font-medium">Không tìm thấy tài liệu</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {keyword ? `Không có kết quả cho "${keyword}"` : "Chưa có tài liệu nào được tải lên"}
          </p>
          {keyword && (
            <Button variant="outline" size="sm" className="mt-4" onClick={clearSearch}>
              Xoá bộ lọc
            </Button>
          )}
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-2">
            {result.items.map((doc, i) => (
              <DocumentRow key={doc.id} doc={doc} index={i} />
            ))}
          </div>

          {/* Pagination */}
          {result.total_pages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Trang {result.page}/{result.total_pages} — {result.total} kết quả
              </p>
              <div className="flex gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => goPage(page - 1)}
                >
                  ← Trước
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= result.total_pages}
                  onClick={() => goPage(page + 1)}
                >
                  Sau →
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function DocumentRow({ doc, index }: { doc: DocumentSearchResult; index: number }) {
  return (
    <Link href={`/documents/${doc.id}`}>
      <Card
        className="transition-all duration-150 hover:border-primary/40 hover:shadow-sm"
        style={{ animationDelay: `${index * 30}ms` }}
      >
        <CardContent className="flex items-center gap-4 p-4">
          {/* File type icon */}
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/8 border border-border">
            <FileTypeIcon type={doc.file_type} />
          </div>

          {/* Main info */}
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-3">
              <h3 className="truncate text-sm font-semibold leading-tight">{doc.title}</h3>
            </div>
            {doc.summary && (
              <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">{doc.summary}</p>
            )}
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              {doc.folder_name && (
                <Badge variant="outline" className="h-5 text-[10px] px-1.5">
                  📁 {doc.folder_name}
                </Badge>
              )}
              {doc.subject && (
                <Badge variant="secondary" className="h-5 text-[10px] px-1.5">
                  {doc.subject}
                </Badge>
              )}
              {doc.tags.slice(0, 3).map((t) => (
                <Badge key={t} variant="outline" className="h-5 text-[10px] px-1.5 text-muted-foreground">
                  #{t}
                </Badge>
              ))}
              <span className="flex items-center gap-1 text-[10px] text-muted-foreground ml-auto">
                <Clock className="h-3 w-3" />
                {formatDate(doc.created_at)}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
