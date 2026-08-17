"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bookmark, FileText } from "lucide-react";
import { socialApi, ApiError } from "@/lib/api";
import type { BookmarkedDocument } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/documents/status-badge";
import { formatDate } from "@/lib/utils";
import { useToast } from "@/lib/toast-context";

export default function BookmarksPage() {
  const { toast } = useToast();
  const [items, setItems] = useState<BookmarkedDocument[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    socialApi
      .listMyBookmarks(1, 50)
      .then((res) => setItems(res.items))
      .catch((err) => {
        toast({
          title: "Không tải được danh sách đã lưu",
          description: err instanceof ApiError ? err.message : undefined,
          variant: "error",
        });
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col gap-3">
        {[...Array(4)].map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-24 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <Bookmark className="h-5 w-5" />
        </div>
        <p className="text-sm text-muted-foreground">Bạn chưa lưu tài liệu nào.</p>
        <Link href="/search" className="text-sm font-medium text-primary hover:underline">
          Tìm kiếm tài liệu để lưu lại
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {items.map((doc) => (
        <Link key={doc.id} href={`/documents/${doc.id}`}>
          <Card className="transition-colors hover:bg-accent/40">
            <CardContent className="flex items-center justify-between gap-4 p-4">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <FileText className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{doc.title}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Đã lưu {formatDate(doc.bookmarked_at)} · {doc.file_type.toUpperCase()}
                  </p>
                </div>
              </div>
              <StatusBadge status={doc.processing_status} />
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  );
}
