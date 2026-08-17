"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Search as SearchIcon, FileText, ChevronLeft, ChevronRight, SlidersHorizontal, X } from "lucide-react";
import { searchApi, ApiError } from "@/lib/api";
import type { DocumentSearchResult, SearchPaginatedResponse } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/utils";
import { useToast } from "@/lib/toast-context";

const PAGE_SIZE = 10;

export default function SearchPage() {
  const { toast } = useToast();
  const [keyword, setKeyword] = useState("");
  const [subject, setSubject] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<SearchPaginatedResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeQuery, setActiveQuery] = useState<{ keyword?: string; subject?: string }>({});
  const [searched, setSearched] = useState(false);

  const runSearch = useCallback(
    async (p: number, query: { keyword?: string; subject?: string }) => {
      setLoading(true);
      try {
        const data = await searchApi.search({
          keyword: query.keyword || undefined,
          subject: query.subject || undefined,
          page: p,
          page_size: PAGE_SIZE,
        });
        setResult(data);
        setSearched(true);
      } catch (err) {
        toast({ title: "Tìm kiếm thất bại", description: err instanceof ApiError ? err.message : undefined, variant: "error" });
      } finally {
        setLoading(false);
      }
    },
    [toast]
  );

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const query = { keyword, subject };
    setActiveQuery(query);
    setPage(1);
    runSearch(1, query);
  }

  function clearSearch() {
    setKeyword("");
    setSubject("");
    const query = {};
    setActiveQuery(query);
    setPage(1);
    runSearch(1, query);
  }

  function goPage(p: number) {
    setPage(p);
    runSearch(p, activeQuery);
  }

  const hasFilters = !!(activeQuery.keyword || activeQuery.subject);

  return (
    <div className="flex flex-col gap-5 animate-fade-in">
      {/* Search bar */}
      <Card>
        <CardContent className="p-4">
          <form onSubmit={onSubmit} className="flex flex-col gap-3">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="search-keyword"
                  placeholder="Tìm theo tiêu đề, thẻ, môn học..."
                  className="pl-9"
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                />
                {keyword && (
                  <button
                    type="button"
                    onClick={() => setKeyword("")}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={() => setShowFilters((v) => !v)}
                className={showFilters ? "border-primary text-primary" : ""}
                title="Bộ lọc nâng cao"
              >
                <SlidersHorizontal className="h-4 w-4" />
              </Button>
              <Button type="submit" className="gradient-brand border-0 text-white hover:opacity-90">
                Tìm kiếm
              </Button>
            </div>

            {showFilters && (
              <div className="flex flex-wrap gap-3 border-t pt-3 animate-slide-up">
                <div className="flex-1 min-w-[160px]">
                  <Input
                    placeholder="Lọc theo môn học..."
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                  />
                </div>
              </div>
            )}
          </form>

          {/* Active filters */}
          {hasFilters && (
            <div className="mt-3 flex items-center gap-2 flex-wrap border-t pt-3">
              <span className="text-xs text-muted-foreground">Đang lọc:</span>
              {activeQuery.keyword && (
                <Badge variant="secondary" className="rounded-full text-xs">
                  Từ khoá: {activeQuery.keyword}
                </Badge>
              )}
              {activeQuery.subject && (
                <Badge variant="secondary" className="rounded-full text-xs">
                  Môn học: {activeQuery.subject}
                </Badge>
              )}
              <Button variant="ghost" size="sm" className="h-5 px-1.5 text-xs text-muted-foreground" onClick={clearSearch}>
                <X className="h-3 w-3 mr-1" /> Xoá bộ lọc
              </Button>
              {result && (
                <span className="ml-auto text-xs text-muted-foreground">{result.total} kết quả</span>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Results */}
      {loading ? (
        <div className="flex flex-col gap-3">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
      ) : !searched ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <SearchIcon className="mb-3 h-10 w-10 text-muted-foreground/30" />
          <p className="text-sm font-medium text-muted-foreground">Nhập từ khoá và nhấn Tìm kiếm</p>
        </div>
      ) : !result || result.items.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border bg-card py-16 text-center shadow-sm">
          <FileText className="mb-3 h-10 w-10 text-muted-foreground/30" />
          <p className="text-sm font-medium">Không tìm thấy kết quả</p>
          <p className="mt-1 text-xs text-muted-foreground">Thử từ khoá khác hoặc xoá bộ lọc</p>
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-3">
            {result.items.map((doc, i) => (
              <ResultCard key={doc.id} doc={doc} index={i} />
            ))}
          </div>

          {result.total_pages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Trang {result.page}/{result.total_pages} — {result.total} kết quả
              </p>
              <div className="flex gap-1.5">
                <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => goPage(page - 1)}>
                  <ChevronLeft className="h-4 w-4" /> Trước
                </Button>
                <Button variant="outline" size="sm" disabled={page >= result.total_pages} onClick={() => goPage(page + 1)}>
                  Sau <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ResultCard({ doc, index }: { doc: DocumentSearchResult; index: number }) {
  return (
    <Link href={`/documents/${doc.id}`}>
      <Card
        className="transition-all duration-150 hover:border-primary/40 hover:shadow-sm"
        style={{ animationDelay: `${index * 40}ms` }}
      >
        <CardContent className="flex gap-3 p-4">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <FileText className="h-4.5 w-4.5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2">
              <h3 className="truncate text-sm font-semibold">{doc.title}</h3>
              <span className="shrink-0 text-xs text-muted-foreground">{formatDate(doc.created_at)}</span>
            </div>
            {doc.summary && (
              <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{doc.summary}</p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {doc.folder_name && <Badge variant="outline" className="text-[10px] h-5">📁 {doc.folder_name}</Badge>}
              {doc.subject && <Badge variant="secondary" className="text-[10px] h-5">{doc.subject}</Badge>}
              {doc.tags.map((t) => (
                <Badge key={t} variant="outline" className="text-[10px] h-5 text-muted-foreground">
                  #{t}
                </Badge>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
