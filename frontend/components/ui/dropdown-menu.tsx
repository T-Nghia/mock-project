"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface DropdownContextValue {
  open: boolean;
  setOpen: (v: boolean) => void;
}

const DropdownContext = React.createContext<DropdownContextValue | undefined>(undefined);

export function DropdownMenu({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <DropdownContext.Provider value={{ open, setOpen }}>
      <div className="relative inline-block" ref={ref}>
        {children}
      </div>
    </DropdownContext.Provider>
  );
}

export function DropdownMenuTrigger({ children }: { children: React.ReactNode }) {
  const ctx = React.useContext(DropdownContext);
  if (!ctx) throw new Error("DropdownMenuTrigger must be used within DropdownMenu");
  return (
    <div onClick={() => ctx.setOpen(!ctx.open)} className="cursor-pointer">
      {children}
    </div>
  );
}

export function DropdownMenuContent({
  align = "end",
  className,
  children,
}: {
  align?: "start" | "end";
  className?: string;
  children: React.ReactNode;
}) {
  const ctx = React.useContext(DropdownContext);
  if (!ctx) throw new Error("DropdownMenuContent must be used within DropdownMenu");
  if (!ctx.open) return null;
  return (
    <div
      className={cn(
        "animate-fade-in absolute z-50 mt-1.5 min-w-[10rem] rounded-md border border-border bg-card p-1 shadow-md",
        align === "end" ? "right-0" : "left-0",
        className
      )}
    >
      {children}
    </div>
  );
}

export function DropdownMenuItem({
  className,
  onClick,
  children,
}: {
  className?: string;
  onClick?: () => void;
  children: React.ReactNode;
}) {
  const ctx = React.useContext(DropdownContext);
  return (
    <button
      type="button"
      onClick={() => {
        onClick?.();
        ctx?.setOpen(false);
      }}
      className={cn(
        "flex w-full items-center gap-2 rounded-sm px-2.5 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground",
        className
      )}
    >
      {children}
    </button>
  );
}

export function DropdownMenuSeparator() {
  return <div className="my-1 h-px bg-border" />;
}
