"use client";

import { useEffect, useState } from "react";
import { Bookmark, Loader2 } from "lucide-react";
import { socialApi, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useToast } from "@/lib/toast-context";
import { cn } from "@/lib/utils";

export function BookmarkButton({ documentId }: { documentId: string }) {
  const { toast } = useToast();
  const [bookmarked, setBookmarked] = useState(false);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(false);

  useEffect(() => {
    let cancelled = false;
    socialApi
      .getBookmarkStatus(documentId)
      .then((res) => {
        if (!cancelled) setBookmarked(res.bookmarked);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  async function toggle() {
    setToggling(true);
    try {
      const res = bookmarked
        ? await socialApi.removeBookmark(documentId)
        : await socialApi.addBookmark(documentId);
      setBookmarked(res.bookmarked);
    } catch (err) {
      toast({
        title: "Không thực hiện được thao tác",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "error",
      });
    } finally {
      setToggling(false);
    }
  }

  return (
    <Button variant="outline" size="sm" onClick={toggle} disabled={loading || toggling}>
      {toggling ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <Bookmark className={cn("h-4 w-4", bookmarked && "fill-primary text-primary")} />
      )}
      {bookmarked ? "Đã lưu" : "Lưu tài liệu"}
    </Button>
  );
}
