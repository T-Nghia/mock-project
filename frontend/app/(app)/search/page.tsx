"use client";

import { useCallback, useEffect, useState } from "react";
import { Search as SearchIcon, FileText, ChevronLeft, ChevronRight } from "lucide-react";
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
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<SearchPaginatedResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeQuery, setActiveQuery] = useState<{ keyword?: string; subject?: string }>({});

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
      } catch (err) {
        toast({ title: "Tìm kiếm thất bại", description: err instanceof ApiError ? err.message : undefined, variant: "error" });
      } finally {
        setLoading(false);
      }
    },
    [toast]
  );

  useEffect(() => {
    runSearch(1, {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const query = { keyword, subject };
    setActiveQuery(query);
    setPage(1);
    runSearch(1, query);
  }

  function goPage(p: number) {
    setPage(p);
    runSearch(p, activeQuery);
  }

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardContent className="p-4">
          <form onSubmit={onSubmit} className="flex flex-wrap gap-3">
            <div className="relative min-w-[240px] flex-1">
              <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Tìm theo tiêu đề, thẻ, môn học..."
                className="pl-9"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
              />
            </div>
            <Input
              placeholder="Lọc theo môn học"
              className="max-w-[200px]"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
            <Button type="submit">Tìm kiếm</Button>
          </form>
        </CardContent>
      </Card>

      {loading ? (
        <div className="flex flex-col gap-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : !result || result.items.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">Không tìm thấy tài liệu phù hợp.</p>
      ) : (
        <>
          <div className="flex flex-col gap-3">
            {result.items.map((doc) => (
              <ResultCard key={doc.id} doc={doc} />
            ))}
          </div>

          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Trang {result.page}/{result.total_pages} — {result.total} kết quả
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => goPage(page - 1)}>
                <ChevronLeft className="h-4 w-4" /> Trước
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= result.total_pages}
                onClick={() => goPage(page + 1)}
              >
                Sau <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function ResultCard({ doc }: { doc: DocumentSearchResult }) {
  return (
    <a href={`/documents/${doc.id}`}>
      <Card className="transition-colors hover:border-primary/40">
        <CardContent className="flex gap-3 p-4">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <FileText className="h-4.5 w-4.5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2">
              <h3 className="truncate font-medium">{doc.title}</h3>
              <span className="shrink-0 text-xs text-muted-foreground">{formatDate(doc.created_at)}</span>
            </div>
            {doc.summary && <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{doc.summary}</p>}
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {doc.folder_name && <Badge variant="outline">{doc.folder_name}</Badge>}
              {doc.subject && <Badge variant="secondary">{doc.subject}</Badge>}
              {doc.tags.map((t) => (
                <Badge key={t} variant="outline">
                  #{t}
                </Badge>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>
    </a>
  );
}
