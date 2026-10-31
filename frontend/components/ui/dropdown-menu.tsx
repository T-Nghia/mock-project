"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface DropdownContextValue {
  open: boolean;
  setOpen: (value: boolean) => void;
  triggerRef: React.RefObject<HTMLButtonElement>;
  initialFocus: React.MutableRefObject<"first" | "last">;
  triggerId: string;
  contentId: string;
  popupRole: "menu" | "dialog";
}

const DropdownContext = React.createContext<DropdownContextValue | undefined>(undefined);

// Chat history uses a compound popover with its own buttons, while account and
// folder actions use menu items. Preserve both existing composition patterns.
function hasMenuItems(children: React.ReactNode): boolean {
  return React.Children.toArray(children).some((child) => {
    if (!React.isValidElement<{ children?: React.ReactNode }>(child)) return false;
    return child.type === DropdownMenuItem || hasMenuItems(child.props.children);
  });
}

export function DropdownMenu({ children, open: controlledOpen, onOpenChange }: { children: React.ReactNode; open?: boolean; onOpenChange?: (open: boolean) => void }) {
  const [internalOpen, setInternalOpen] = React.useState(false);
  const open = controlledOpen ?? internalOpen;
  const setOpen = React.useCallback((value: boolean) => {
    if (controlledOpen === undefined) setInternalOpen(value);
    onOpenChange?.(value);
  }, [controlledOpen, onOpenChange]);
  const ref = React.useRef<HTMLDivElement>(null);
  const triggerRef = React.useRef<HTMLButtonElement>(null);
  const initialFocus = React.useRef<"first" | "last">("first");
  const id = React.useId();
  const popupRole = hasMenuItems(children) ? "menu" : "dialog";

  React.useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open, setOpen]);

  return (
    <DropdownContext.Provider value={{ open, setOpen, triggerRef, initialFocus, triggerId: id + "-trigger", contentId: id + "-content", popupRole }}>
      <div
        className="relative inline-block"
        ref={ref}
        onBlur={(event) => {
          if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget as Node)) setOpen(false);
        }}
      >
        {children}
      </div>
    </DropdownContext.Provider>
  );
}

export function DropdownMenuTrigger({ children, className, onClick, onKeyDown, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const ctx = React.useContext(DropdownContext);
  if (!ctx) throw new Error("DropdownMenuTrigger must be used within DropdownMenu");
  return (
    <button
      {...props}
      type="button"
      ref={ctx.triggerRef}
      id={ctx.triggerId}
      aria-haspopup={ctx.popupRole}
      aria-expanded={ctx.open}
      aria-controls={ctx.open ? ctx.contentId : undefined}
      className={cn("rounded-md", className)}
      onClick={(event) => {
        onClick?.(event);
        if (event.defaultPrevented) return;
        ctx.initialFocus.current = "first";
        ctx.setOpen(!ctx.open);
      }}
      onKeyDown={(event) => {
        onKeyDown?.(event);
        if (event.defaultPrevented) return;
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          ctx.initialFocus.current = event.key === "ArrowUp" ? "last" : "first";
          ctx.setOpen(true);
        }
      }}
    >
      {children}
    </button>
  );
}

export function DropdownMenuContent({ align = "end", className, children }: { align?: "start" | "end"; className?: string; children: React.ReactNode }) {
  const ctx = React.useContext(DropdownContext);
  const ref = React.useRef<HTMLDivElement>(null);
  const typeahead = React.useRef({ value: "", time: 0 });
  if (!ctx) throw new Error("DropdownMenuContent must be used within DropdownMenu");
  const { open, initialFocus } = ctx;

  React.useEffect(() => {
    if (!open || !ref.current) return;
    const items = ref.current.querySelectorAll<HTMLElement>("button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled)");
    const index = initialFocus.current === "last" ? items.length - 1 : 0;
    items[index]?.focus({ preventScroll: true });
  }, [open, initialFocus]);

  if (!open) return null;
  return (
    <div
      ref={ref}
      id={ctx.contentId}
      role={ctx.popupRole}
      aria-labelledby={ctx.triggerId}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          ctx.setOpen(false);
          ctx.triggerRef.current?.focus();
          return;
        }
        if (ctx.popupRole !== "menu") return;
        if (event.key === "Tab") {
          ctx.setOpen(false);
          ctx.triggerRef.current?.focus();
          return;
        }
        const items = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)'));
        const index = items.indexOf(document.activeElement as HTMLElement);
        let next: number | undefined;
        if (event.key === "ArrowDown") next = (index + 1) % items.length;
        if (event.key === "ArrowUp") next = (index - 1 + items.length) % items.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = items.length - 1;
        if (next !== undefined) {
          event.preventDefault();
          items[next]?.focus();
        } else if (event.key.length === 1 && !event.ctrlKey && !event.altKey && !event.metaKey && event.key !== " ") {
          const now = Date.now();
          typeahead.current.value = (now - typeahead.current.time < 500 ? typeahead.current.value : "") + event.key.toLocaleLowerCase("vi");
          typeahead.current.time = now;
          const ordered = [...items.slice(index + 1), ...items.slice(0, index + 1)];
          ordered.find((item) => item.textContent?.trim().toLocaleLowerCase("vi").startsWith(typeahead.current.value))?.focus();
        }
      }}
      className={cn(
        "absolute z-50 mt-2 min-w-[11rem] max-w-[calc(100vw-2rem)] animate-fade-in rounded-lg border border-border bg-card p-1.5 shadow-popover",
        align === "end" ? "right-0" : "left-0",
        className
      )}
    >
      {children}
    </div>
  );
}

export function DropdownMenuItem({ className, onClick, children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const ctx = React.useContext(DropdownContext);
  return (
    <button
      {...props}
      type="button"
      role="menuitem"
      tabIndex={-1}
      onClick={(event) => {
        // Return focus before an action opens a dialog, so it can restore focus
        // to a persistent trigger instead of the disappearing menu item.
        ctx?.setOpen(false);
        ctx?.triggerRef.current?.focus({ preventScroll: true });
        onClick?.(event);
      }}
      className={cn(
        "flex min-h-10 w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
        className
      )}
    >
      {children}
    </button>
  );
}

export function DropdownMenuSeparator() {
  return <div role="separator" className="my-1.5 h-px bg-border" />;
}
