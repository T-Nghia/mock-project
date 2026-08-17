"use client";

import { useEffect, useState } from "react";
import { MessageSquare, Send, Trash2, Loader2 } from "lucide-react";
import { socialApi, ApiError } from "@/lib/api";
import type { Comment } from "@/lib/types";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/lib/toast-context";
import { formatDate, initials } from "@/lib/utils";

export function CommentsSection({ documentId }: { documentId: string }) {
  const { toast } = useToast();
  const { user } = useAuth();
  const [comments, setComments] = useState<Comment[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  function load() {
    setLoading(true);
    socialApi
      .listComments(documentId, 1, 50)
      .then((res) => {
        setComments(res.items);
        setTotal(res.total);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = content.trim();
    if (!trimmed) return;
    setSubmitting(true);
    try {
      const comment = await socialApi.addComment(documentId, trimmed);
      setComments((prev) => [comment, ...prev]);
      setTotal((t) => t + 1);
      setContent("");
    } catch (err) {
      toast({
        title: "Không gửi được bình luận",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "error",
      });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(commentId: string) {
    setDeletingId(commentId);
    try {
      await socialApi.deleteComment(commentId);
      setComments((prev) => prev.filter((c) => c.id !== commentId));
      setTotal((t) => Math.max(0, t - 1));
    } catch (err) {
      toast({
        title: "Không xoá được bình luận",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "error",
      });
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div>
      <h3 className="mb-3 flex items-center gap-1.5 text-sm font-medium">
        <MessageSquare className="h-4 w-4" /> Bình luận {total > 0 && `(${total})`}
      </h3>

      <form onSubmit={handleSubmit} className="mb-4 flex items-start gap-2">
        <Textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Viết bình luận về tài liệu này…"
          className="min-h-[44px] flex-1 resize-none"
          maxLength={2000}
        />
        <Button type="submit" size="icon" disabled={!content.trim() || submitting}>
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </Button>
      </form>

      {loading ? (
        <p className="text-sm text-muted-foreground">Đang tải bình luận…</p>
      ) : comments.length === 0 ? (
        <p className="text-sm text-muted-foreground">Chưa có bình luận nào. Hãy là người đầu tiên!</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {comments.map((c) => (
            <li key={c.id} className="flex gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-medium text-primary">
                {initials(c.author_name)}
              </div>
              <div className="min-w-0 flex-1 rounded-lg bg-muted/50 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{c.author_name}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">{formatDate(c.created_at)}</span>
                    {(user?.id === c.user_id || user?.role === "admin") && (
                      <button
                        onClick={() => handleDelete(c.id)}
                        disabled={deletingId === c.id}
                        className="text-muted-foreground hover:text-destructive disabled:opacity-50"
                        aria-label="Xoá bình luận"
                      >
                        {deletingId === c.id ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="h-3.5 w-3.5" />
                        )}
                      </button>
                    )}
                  </div>
                </div>
                <p className="mt-0.5 whitespace-pre-wrap text-sm text-foreground">{c.content}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
