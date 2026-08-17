"use client";

import { useEffect, useRef, useState } from "react";
import { Send, Sparkles, Loader2, Quote } from "lucide-react";
import { chatApi, ApiError } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/lib/toast-context";
import { cn } from "@/lib/utils";

interface ChatPanelProps {
  documentId: string;
  suggestedQuestions: string[];
}

export function ChatPanel({ documentId, suggestedQuestions }: ChatPanelProps) {
  const { toast } = useToast();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [initializing, setInitializing] = useState(true);
  const [asking, setAsking] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    chatApi
      .createSession(documentId)
      .then((session) => {
        if (cancelled) return;
        setSessionId(session.id);
        return chatApi.getSession(session.id);
      })
      .then((detail) => {
        if (cancelled || !detail) return;
        setMessages(detail.messages);
      })
      .catch((err) => {
        toast({
          title: "Không thể khởi tạo phiên trò chuyện",
          description: err instanceof ApiError ? err.message : undefined,
          variant: "error",
        });
      })
      .finally(() => {
        if (!cancelled) setInitializing(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, asking]);

  async function sendQuestion(content: string) {
    const trimmed = content.trim();
    if (!trimmed || !sessionId || asking) return;

    const userMessage: ChatMessage = {
      id: `local-${Date.now()}`,
      role: "user",
      content: trimmed,
      sources: [],
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setAsking(true);

    try {
      const answer = await chatApi.ask(sessionId, trimmed);
      const assistantMessage: ChatMessage = {
        id: `local-${Date.now()}-a`,
        role: "assistant",
        content: answer.answer,
        sources: answer.sources,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      toast({
        title: "Không lấy được câu trả lời",
        description: err instanceof ApiError ? err.message : undefined,
        variant: "error",
      });
      setMessages((prev) => prev.filter((m) => m.id !== userMessage.id));
      setInput(trimmed);
    } finally {
      setAsking(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    sendQuestion(input);
  }

  if (initializing) {
    return (
      <div className="flex flex-1 items-center justify-center py-16">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex h-[70vh] flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto px-1 py-2">
        {messages.length === 0 && (
          <div className="flex flex-col items-center gap-4 py-8 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Sparkles className="h-5 w-5" />
            </div>
            <p className="text-sm text-muted-foreground">
              Đặt câu hỏi về nội dung tài liệu này, trợ lý AI sẽ trả lời dựa trên nội dung đã upload.
            </p>
            {suggestedQuestions.length > 0 && (
              <div className="flex w-full flex-col gap-2">
                {suggestedQuestions.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => sendQuestion(q)}
                    className="rounded-md border border-border bg-muted/40 px-3 py-2 text-left text-sm text-foreground transition-colors hover:bg-accent"
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((m) => (
          <div key={m.id} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
            <div
              className={cn(
                "max-w-[85%] rounded-lg px-3.5 py-2.5 text-sm leading-relaxed",
                m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted text-foreground"
              )}
            >
              <p className="whitespace-pre-wrap">{m.content}</p>
              {m.sources.length > 0 && (
                <div className="mt-2.5 space-y-1.5 border-t border-border/40 pt-2">
                  {m.sources.map((s) => (
                    <div key={s.chunk_id} className="flex items-start gap-1.5 text-xs text-muted-foreground">
                      <Quote className="mt-0.5 h-3 w-3 shrink-0" />
                      <span>&ldquo;{s.quote}&rdquo;</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {asking && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-lg bg-muted px-3.5 py-2.5 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Đang suy nghĩ…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} className="mt-3 flex items-end gap-2 border-t border-border pt-3">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              sendQuestion(input);
            }
          }}
          placeholder="Hỏi điều gì đó về tài liệu này…"
          className="min-h-[44px] flex-1 resize-none"
          disabled={!sessionId || asking}
        />
        <Button type="submit" size="icon" disabled={!input.trim() || !sessionId || asking}>
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </div>
  );
}
