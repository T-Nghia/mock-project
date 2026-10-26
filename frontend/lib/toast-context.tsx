"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, XCircle, Info, X } from "lucide-react";
import { cn } from "./utils";

type ToastVariant = "success" | "error" | "info";

interface Toast {
  id: number;
  title: string;
  description?: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  toast: (t: { title: string; description?: string; variant?: ToastVariant }) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

let counter = 0;

const ICONS: Record<ToastVariant, React.ElementType> = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
};

const STYLES: Record<ToastVariant, string> = {
  success: "border-success/25 bg-card text-success",
  error: "border-destructive/25 bg-card text-destructive",
  info: "border-border bg-card text-card-foreground",
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [portalTarget, setPortalTarget] = useState<HTMLElement | null>(null);

  useEffect(() => {
    // Keep notifications visible and reachable above a native modal dialog.
    const syncTarget = () => {
      const dialogs = document.querySelectorAll<HTMLDialogElement>("dialog[open]");
      setPortalTarget(dialogs.item(dialogs.length - 1) ?? document.body);
    };
    syncTarget();
    const observer = new MutationObserver((records) => {
      if (records.some((record) => record.type === "attributes" || [...Array.from(record.addedNodes), ...Array.from(record.removedNodes)].some((node) => node instanceof HTMLDialogElement))) {
        syncTarget();
      }
    });
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["open"] });
    return () => observer.disconnect();
  }, []);

  const toast = useCallback((t: { title: string; description?: string; variant?: ToastVariant }) => {
    const id = ++counter;
    setToasts((prev) => [...prev, { id, variant: "info", ...t }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== id));
    }, 4500);
  }, []);

  const dismiss = (id: number) => setToasts((prev) => prev.filter((x) => x.id !== id));

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      {portalTarget && createPortal(<div aria-live="polite" aria-relevant="additions" className="pointer-events-none fixed bottom-4 left-4 right-4 z-[100] flex flex-col gap-2 sm:left-auto sm:w-96 sm:max-w-[calc(100vw-2rem)]">
        {toasts.map((t) => {
          const Icon = ICONS[t.variant];
          return (
            <div
              key={t.id}
              className={cn(
                "pointer-events-auto animate-slide-up flex items-start gap-3 rounded-lg border p-4 shadow-popover",
                STYLES[t.variant]
              )}
            >
              <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
              <div className="min-w-0 flex-1 break-words">
                <p className="text-sm font-medium">{t.title}</p>
                {t.description && <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{t.description}</p>}
              </div>
              <button type="button" aria-label="Đóng thông báo" onClick={() => dismiss(t.id)} className="-m-2 flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
                <X aria-hidden="true" className="h-4 w-4" />
              </button>
            </div>
          );
        })}
      </div>, portalTarget)}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
