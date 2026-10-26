"use client";

import { useEffect, useRef, useState } from "react";
import { Send, Sparkles, Loader2, Quote, Plus, History, Trash2, ChevronDown, ArrowUpRight } from "lucide-react";
import { chatApi, ApiError } from "@/lib/api";
import type { ChatMessage, ChatSession } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent } from "@/components/ui/dropdown-menu";
import { useToast } from "@/lib/toast-context";
import { cn, formatDate } from "@/lib/utils";

interface ChatPanelProps {
  documentId: string;
  suggestedQuestions: string[];
}

export function ChatPanel({ documentId, suggestedQuestions }: ChatPanelProps) {
  const { toast } = useToast();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [initializing, setInitializing] = useState(true);
  const [initialError, setInitialError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [switching, setSwitching] = useState(false);
  const [asking, setAsking] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const messageListRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const operationRef = useRef(false);
  const mountedRef = useRef(false);
  const draftsRef = useRef<Record<string, string>>({});
  const busy = initializing || switching || asking;

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setInitializing(true);
    setInitialError(null);
    async function initialize() {
      try {
        const list = await chatApi.listSessionsForDocument(documentId);
        if (cancelled) return;
        setSessions(list);
        if (list.length > 0) {
          const detail = await chatApi.getSession(list[0].id);
          if (cancelled) return;
          setSessionId(detail.id);
          setMessages(detail.messages);
        }
        // Reading a document (including Strict Mode remounts) never creates a session.
      } catch (err) {
        if (!cancelled) setInitialError(err instanceof ApiError ? err.message : "Không tải được lịch sử hội thoại.");
      } finally {
        if (!cancelled) setInitializing(false);
      }
    }
    void initialize();
    return () => { cancelled = true; };
  }, [documentId, attempt]);

  useEffect(() => {
    // Scroll only the message list, never the document or the whole workspace.
    const list = messageListRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [messages, asking, error]);

  function reportError(title: string, err: unknown) {
    if (!mountedRef.current) return;
    const description = err instanceof ApiError ? err.message : "Vui lòng thử lại.";
    setError(`${title}. ${description}`);
    toast({ title, description, variant: "error" });
  }

  function rememberDraft() {
    draftsRef.current[sessionId ?? "new"] = input;
  }

  async function createSession() {
    const session = await chatApi.createSession(documentId);
    if (mountedRef.current) {
      setSessions((prev) => [session, ...prev.filter((item) => item.id !== session.id)]);
      setSessionId(session.id);
      setMessages([]);
    }
    return session.id;
  }

  async function loadSession(id: string) {
    if (busy || operationRef.current) return;
    setHistoryOpen(false);
    if (id === sessionId) {
      inputRef.current?.focus({ preventScroll: true });
      return;
    }
    operationRef.current = true;
    setSwitching(true);
    setError(null);
    rememberDraft();
    try {
      const detail = await chatApi.getSession(id);
      if (!mountedRef.current) return;
      setSessionId(detail.id);
      setMessages(detail.messages);
      setInput(draftsRef.current[id] ?? "");
    } catch (err) {
      reportError("Không tải được cuộc trò chuyện", err);
    } finally {
      operationRef.current = false;
      if (mountedRef.current) {
        setSwitching(false);
        requestAnimationFrame(() => inputRef.current?.focus({ preventScroll: true }));
      }
    }
  }

  async function startNewSession() {
    if (busy || initialError || operationRef.current) return;
    operationRef.current = true;
    setSwitching(true);
    setError(null);
    rememberDraft();
    try {
      await createSession();
      if (mountedRef.current) setInput("");
    } catch (err) {
      reportError("Không thể tạo cuộc trò chuyện mới", err);
    } finally {
      operationRef.current = false;
      if (mountedRef.current) setSwitching(false);
    }
  }

  async function sendQuestion(content: string) {
    const trimmed = content.trim();
    if (!trimmed || busy || initialError || operationRef.current) return;
    // A synchronous lock also covers rapid clicks before React re-renders.
    operationRef.current = true;
    setAsking(true);
    setError(null);
    const userMessage: ChatMessage = {
      id: `local-${Date.now()}`, role: "user", content: trimmed, sources: [], created_at: new Date().toISOString(),
    };
    let targetId = sessionId;
    try {
      if (!targetId) targetId = await createSession();
      if (!mountedRef.current) return;
      setMessages((prev) => [...prev, userMessage]);
      setInput("");
      draftsRef.current[targetId] = "";
      const answer = await chatApi.ask(targetId, trimmed);
      if (!mountedRef.current) return;
      setMessages((prev) => [...prev, {
        id: `local-${Date.now()}-a`, role: "assistant", content: answer.answer,
        sources: answer.sources, created_at: new Date().toISOString(),
      }]);
    } catch (err) {
      if (!mountedRef.current) return;
      reportError("Không lấy được câu trả lời", err);
      setMessages((prev) => prev.filter((message) => message.id !== userMessage.id));
      setInput(trimmed);
      draftsRef.current[targetId ?? "new"] = trimmed;
    } finally {
      operationRef.current = false;
      if (mountedRef.current) {
        setAsking(false);
        // Wait for the disabled textarea to become focusable again.
        requestAnimationFrame(() => inputRef.current?.focus({ preventScroll: true }));
      }
    }
  }

  async function handleDeleteSession(id: string) {
    if (busy || operationRef.current) return;
    operationRef.current = true;
    setSwitching(true);
    setError(null);
    try {
      await chatApi.deleteSession(id);
      if (!mountedRef.current) return;
      const remaining = sessions.filter((session) => session.id !== id);
      setSessions(remaining);
      delete draftsRef.current[id];
      if (id === sessionId) {
        setSessionId(null);
        setMessages([]);
        setInput("");
        // Deleting the last session leaves an empty state, without a POST.
        if (remaining.length > 0) {
          const detail = await chatApi.getSession(remaining[0].id);
          if (!mountedRef.current) return;
          setSessionId(detail.id);
          setMessages(detail.messages);
          setInput(draftsRef.current[detail.id] ?? "");
        }
      }
    } catch (err) {
      reportError("Không hoàn tất thao tác với lịch sử", err);
    } finally {
      operationRef.current = false;
      if (mountedRef.current) setSwitching(false);
    }
  }

  const currentSession = sessions.find((session) => session.id === sessionId);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="shrink-0 border-b border-border px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"><Sparkles aria-hidden="true" className="h-4 w-4" /></span>
          <div className="min-w-0 flex-1"><h2 className="text-sm font-semibold">Trợ lý AI</h2><p className="truncate text-xs text-muted-foreground">Cùng bạn khám phá tài liệu</p></div>
          <Button variant="ghost" size="icon" aria-label="Cuộc trò chuyện mới" title="Cuộc trò chuyện mới" onClick={startNewSession} disabled={busy || !!initialError}><Plus aria-hidden="true" className="h-4 w-4" /></Button>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <DropdownMenu open={historyOpen} onOpenChange={setHistoryOpen}>
            <DropdownMenuTrigger disabled={busy || !!initialError} className="flex min-h-9 items-center gap-1.5 rounded-md border border-border px-2.5 text-xs text-muted-foreground hover:bg-accent disabled:opacity-50">
              <History aria-hidden="true" className="h-3.5 w-3.5" /> Lịch sử ({sessions.length}) <ChevronDown aria-hidden="true" className="h-3 w-3" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="max-h-64 w-64 overflow-y-auto">
              {sessions.length === 0 && <p className="p-3 text-xs text-muted-foreground">Chưa có cuộc trò chuyện nào.</p>}
              {sessions.map((session) => (
                <div key={session.id} className={cn("flex items-center gap-1 rounded-md p-1", session.id === sessionId && "bg-primary/5")}>
                  <button disabled={busy} aria-current={session.id === sessionId ? "true" : undefined} className="min-h-10 min-w-0 flex-1 rounded-md px-2 text-left text-sm hover:bg-accent disabled:opacity-50" onClick={() => loadSession(session.id)} title={session.title}>
                    <span className="block truncate">{session.title || "Cuộc trò chuyện mới"}</span><span className="text-[11px] text-muted-foreground">{formatDate(session.created_at)}</span>
                  </button>
                  <Button size="icon" variant="ghost" disabled={busy} onClick={() => handleDeleteSession(session.id)} aria-label={`Xóa cuộc trò chuyện ${session.title || formatDate(session.created_at)}`}><Trash2 aria-hidden="true" className="h-3.5 w-3.5" /></Button>
                </div>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <p className="min-w-0 truncate text-xs text-muted-foreground" title={currentSession?.title}>{currentSession?.title || "Cuộc trò chuyện mới"}</p>
        </div>
      </header>

      <div ref={messageListRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-5 sm:px-5">
        {initializing || switching ? (
          <p role="status" className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground"><Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />Đang tải hội thoại…</p>
        ) : initialError ? (
          <div className="space-y-3 py-8 text-center"><p role="alert" className="text-sm text-destructive">{initialError}</p><Button size="sm" variant="outline" onClick={() => setAttempt((value) => value + 1)}>Thử lại lịch sử</Button></div>
        ) : (
          <>
            {messages.length === 0 && !asking && (
              <div className="flex flex-col items-center py-5 text-center">
                <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border border-primary/10 bg-primary/5 text-primary"><Sparkles aria-hidden="true" className="h-6 w-6" /></div>
                <h3 className="text-base font-semibold tracking-tight">Hiểu sâu hơn, từng câu hỏi</h3>
                <p className="mb-6 mt-2 max-w-xs text-sm leading-6 text-muted-foreground">Đặt câu hỏi, tìm ý chính và khám phá nội dung dựa trên tài liệu của bạn.</p>
                {suggestedQuestions.length > 0 && <div className="w-full space-y-2 text-left">
                  <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Gợi ý bắt đầu</p>
                  {suggestedQuestions.map((question, index) => <button key={index} onClick={() => sendQuestion(question)} disabled={busy} className="group flex w-full items-start gap-3 rounded-lg border border-border p-3 text-left text-sm leading-6 transition-colors hover:border-primary/30 hover:bg-primary/5 disabled:opacity-50"><span className="min-w-0 flex-1 break-words">{question}</span><ArrowUpRight aria-hidden="true" className="mt-1 h-4 w-4 shrink-0 text-muted-foreground group-hover:text-primary" /></button>)}
                </div>}
              </div>
            )}
            <div role="log" aria-label="Tin nhắn hội thoại" aria-live="polite" aria-relevant="additions" className="space-y-6">
              {messages.map((message) => (
                <article key={message.id} aria-label={message.role === "user" ? "Tin nhắn của bạn" : "Câu trả lời của trợ lý AI"} className={cn("min-w-0", message.role === "user" && "ml-6")}>
                  <p className={cn("mb-2 flex items-center gap-1.5 text-xs font-semibold", message.role === "user" ? "justify-end text-muted-foreground" : "text-primary")}>
                    {message.role === "assistant" && <Sparkles aria-hidden="true" className="h-3.5 w-3.5" />}{message.role === "user" ? "Bạn" : "Trợ lý AI"}
                  </p>
                  <div className={cn("whitespace-pre-wrap break-words text-sm leading-7", message.role === "user" && "rounded-xl rounded-tr-sm bg-muted/80 px-4 py-3")}>{message.content}</div>
                  {message.sources.length > 0 && <div className="mt-4 space-y-2">
                    <p className="text-xs font-medium text-muted-foreground">Nguồn tham khảo · {message.sources.length}</p>
                    {message.sources.map((source, index) => <details key={`${source.chunk_id}-${index}`} className="rounded-lg border border-border bg-muted/30 p-3">
                      <summary className="cursor-pointer break-words text-xs font-medium leading-5"><Quote aria-hidden="true" className="mr-1 inline h-3 w-3 text-primary" />[{index + 1}] {source.heading_path.length ? source.heading_path.join(" › ") : `Đoạn trích ${index + 1}`}</summary>
                      <blockquote className="mt-2 whitespace-pre-wrap break-words border-l-2 border-primary/20 pl-3 text-xs leading-6 text-muted-foreground">{source.quote}</blockquote>
                    </details>)}
                  </div>}
                </article>
              ))}
            </div>
            {asking && <p role="status" className="mt-5 flex items-center gap-2 text-sm text-muted-foreground"><Loader2 aria-hidden="true" className="h-4 w-4 animate-spin text-primary" />Đang tìm câu trả lời…</p>}
            {error && <p role="alert" className="mt-4 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-xs leading-5 text-destructive">{error}</p>}
          </>
        )}
      </div>

      <form onSubmit={(event) => { event.preventDefault(); void sendQuestion(input); }} className="shrink-0 border-t border-border bg-card p-3 sm:p-4">
        <div className="rounded-xl border border-input bg-background p-2 focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/10">
          <Textarea ref={inputRef} aria-label="Câu hỏi cho trợ lý AI" value={input} onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void sendQuestion(input); }
            }}
            placeholder="Hỏi điều gì đó về tài liệu này…" rows={2} className="min-h-14 resize-none border-0 bg-transparent px-2 shadow-none focus-visible:ring-0" disabled={busy || !!initialError} />
          <div className="flex items-center justify-between gap-2 px-1 pb-1">
            <span className="text-[10px] text-muted-foreground">Enter gửi · Shift + Enter xuống dòng</span>
            <Button type="submit" size="icon" className="h-8 w-8 rounded-lg" aria-label="Gửi câu hỏi" disabled={!input.trim() || busy || !!initialError}><Send aria-hidden="true" className="h-3.5 w-3.5" /></Button>
          </div>
        </div>
        <p className="mt-2 text-center text-[10px] leading-4 text-muted-foreground">Đối chiếu câu trả lời AI với nguồn trích dẫn trong tài liệu.</p>
      </form>
    </div>
  );
}
