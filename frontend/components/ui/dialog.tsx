"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DialogProps {
  id?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
  variant?: "center" | "drawer";
}

interface DialogContextValue {
  titleId: string;
  descriptionId: string;
  setHasDescription: React.Dispatch<React.SetStateAction<boolean>>;
}

const DialogContext = React.createContext<DialogContextValue | undefined>(undefined);
let openDialogs = 0;
let previousBodyOverflow = "";

export function Dialog({ id, open, onOpenChange, children, variant = "center" }: DialogProps) {
  const [mounted, setMounted] = React.useState(false);
  const [hasDescription, setHasDescription] = React.useState(false);
  const dialogRef = React.useRef<HTMLDialogElement>(null);
  const generatedId = React.useId();
  const titleId = generatedId + "-title";
  const descriptionId = generatedId + "-description";

  React.useEffect(() => setMounted(true), []);

  React.useEffect(() => {
    const dialog = dialogRef.current;
    if (!mounted || !open || !dialog) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;

    // Native modal dialogs keep the background inert and handle keyboard focus.
    dialog.showModal();
    if (openDialogs === 0) {
      previousBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }
    openDialogs += 1;

    return () => {
      dialog.close();
      openDialogs -= 1;
      if (openDialogs === 0) document.body.style.overflow = previousBodyOverflow;
      if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
    };
  }, [mounted, open]);

  if (!mounted || !open) return null;

  return createPortal(
    <DialogContext.Provider value={{ titleId, descriptionId, setHasDescription }}>
      <dialog
        id={id}
        ref={dialogRef}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={hasDescription ? descriptionId : undefined}
        onCancel={(event) => {
          event.preventDefault();
          onOpenChange(false);
        }}
        onKeyDown={(event) => {
          if (event.key !== "Tab" || event.defaultPrevented) return;
          const dialog = event.currentTarget;
          const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(
            'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), iframe, [tabindex]:not([tabindex="-1"])'
          )).filter((element) => element.tabIndex >= 0 && element.getClientRects().length > 0 && getComputedStyle(element).visibility !== "hidden");
          const first = focusable[0];
          const last = focusable[focusable.length - 1];
          if (!first) {
            event.preventDefault();
            dialog.focus();
          } else if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) {
            event.preventDefault();
            last.focus();
          } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog)) {
            event.preventDefault();
            first.focus();
          }
        }}
        className="fixed inset-0 m-0 h-dvh max-h-none w-screen max-w-none overflow-y-auto border-0 bg-transparent p-0 text-foreground backdrop:bg-slate-950/35 backdrop:backdrop-blur-[2px]"
      >
        <div
          className={cn("flex min-h-full", variant === "drawer" ? "h-full items-stretch" : "items-center justify-center p-4 sm:p-6")}
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              event.preventDefault();
              onOpenChange(false);
            }
          }}
        >
          <div
            className={cn("relative animate-slide-up", variant === "drawer" ? "h-full w-[min(20rem,90vw)]" : "w-full")}
            onClick={(event) => {
              if (event.target === event.currentTarget) {
                event.preventDefault();
                onOpenChange(false);
              }
            }}
          >
            {children}
          </div>
        </div>
      </dialog>
    </DialogContext.Provider>,
    document.body
  );
}

export function DialogContent({ className, children, onClose }: { className?: string; children: React.ReactNode; onClose?: () => void }) {
  return (
    <div className={cn("relative mx-auto w-full max-w-lg rounded-xl border border-border bg-card p-5 shadow-popover sm:p-6", className)}>
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          aria-label="Đóng hộp thoại"
          className="absolute right-2.5 top-2.5 z-10 flex h-11 w-11 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <X aria-hidden="true" className="h-4 w-4" />
        </button>
      )}
      {children}
    </div>
  );
}

export function DialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mb-5 flex flex-col gap-1.5 pr-9", className)} {...props} />;
}

export function DialogTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  const ctx = React.useContext(DialogContext);
  return <h2 id={ctx?.titleId} className={cn("text-lg font-semibold leading-7 tracking-tight", className)} {...props} />;
}

export function DialogDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  const ctx = React.useContext(DialogContext);
  const setHasDescription = ctx?.setHasDescription;
  React.useEffect(() => {
    setHasDescription?.(true);
    return () => setHasDescription?.(false);
  }, [setHasDescription]);
  return <p id={ctx?.descriptionId} className={cn("text-sm leading-relaxed text-muted-foreground", className)} {...props} />;
}

export function DialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mt-6 flex flex-wrap justify-end gap-2", className)} {...props} />;
}
