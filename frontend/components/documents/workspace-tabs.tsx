"use client";

import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface WorkspaceTabsProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  tabs: { value: string; label: string; icon?: LucideIcon }[];
  className?: string;
}

export function WorkspaceTabs({ id, label, value, onChange, tabs, className }: WorkspaceTabsProps) {
  return (
    <div role="tablist" aria-label={label} className={cn("flex shrink-0 gap-1 rounded-lg bg-muted/70 p-1", className)}>
      {tabs.map((tab, index) => (
        <button key={tab.value} type="button" role="tab" id={`${id}-${tab.value}-tab`}
          aria-selected={value === tab.value} aria-controls={`${id}-${tab.value}-panel`} tabIndex={value === tab.value ? 0 : -1}
          onClick={() => onChange(tab.value)}
          onKeyDown={(event) => {
            let next: number | undefined;
            if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
            if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
            if (event.key === "Home") next = 0;
            if (event.key === "End") next = tabs.length - 1;
            if (next === undefined) return;
            event.preventDefault();
            onChange(tabs[next].value);
            document.getElementById(`${id}-${tabs[next].value}-tab`)?.focus();
          }}
          className={cn("flex min-h-9 flex-auto items-center justify-center gap-2 whitespace-nowrap rounded-md px-2.5 py-2 text-xs font-medium transition-colors", value === tab.value ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:bg-card/60 hover:text-foreground")}>
          {tab.icon && <tab.icon aria-hidden="true" className="h-4 w-4 shrink-0" />}{tab.label}
        </button>
      ))}
    </div>
  );
}
