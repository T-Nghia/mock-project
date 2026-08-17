"use client";

import { useEffect, useState } from "react";
import { Star, Loader2 } from "lucide-react";
import { socialApi, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast-context";
import { cn } from "@/lib/utils";

export function RatingStars({ documentId }: { documentId: string }) {
  const { toast } = useToast();
  const [average, setAverage] = useState<number | null>(null);
  const [count, setCount] = useState(0);
  const [myScore, setMyScore] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    socialApi
      .getRatingSummary(documentId)
      .then((res) => {
        if (cancelled) return;
        setAverage(res.average);
        setCount(res.count);
        setMyScore(res.my_score);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  async function handleRate(score: number) {
    setSubmitting(true);
    try {
      const res =
        myScore === score
          ? await socialApi.removeRating(documentId)
          : await socialApi.setRating(documentId, score);
      setAverage(res.average);
      setCount(res.count);
      setMyScore(res.my_score);
    } catch (err) {
      toast({
        title: "Không gửi được đánh giá",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "error",
      });
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />;
  }

  const display = hovered ?? myScore ?? 0;

  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center" onMouseLeave={() => setHovered(null)}>
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            type="button"
            disabled={submitting}
            onMouseEnter={() => setHovered(star)}
            onClick={() => handleRate(star)}
            className="p-0.5 disabled:cursor-not-allowed"
            aria-label={`Đánh giá ${star} sao`}
          >
            <Star
              className={cn(
                "h-4 w-4 transition-colors",
                star <= display ? "fill-warning text-warning" : "text-muted-foreground"
              )}
            />
          </button>
        ))}
      </div>
      <span className="text-xs text-muted-foreground">
        {average !== null ? `${average.toFixed(1)} (${count} đánh giá)` : "Chưa có đánh giá"}
      </span>
    </div>
  );
}
