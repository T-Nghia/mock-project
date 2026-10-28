"use client";

import { useState } from "react";
import { ChevronRight, Folder, FolderOpen, MoreVertical, Pencil, Plus, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FolderTreeNode } from "@/lib/types";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

interface FolderTreeProps {
  nodes: FolderTreeNode[];
  selectedId: string | null;
  onSelect: (node: FolderTreeNode) => void;
  onCreateChild: (parent: FolderTreeNode | null) => void;
  onRename: (node: FolderTreeNode) => void;
  onDelete: (node: FolderTreeNode) => void;
}

function TreeNode({
  node,
  depth,
  selectedId,
  onSelect,
  onCreateChild,
  onRename,
  onDelete,
}: {
  node: FolderTreeNode;
  depth: number;
} & Omit<FolderTreeProps, "nodes">) {
  const [open, setOpen] = useState(true);
  const hasChildren = node.children.length > 0;
  const selected = selectedId === node.id;

  return (
    <div>
      <div
        className={cn(
          "group flex min-w-0 items-center gap-1 rounded-lg py-1 pr-1 text-sm hover:bg-accent",
          selected && "bg-primary/10 text-primary font-medium"
        )}
        style={{ paddingLeft: `${Math.min(depth, 4) * 10 + 4}px` }}
      >
        <button
          type="button"
          aria-label={`${open ? "Thu gọn" : "Mở rộng"} thư mục ${node.name}`}
          aria-expanded={hasChildren ? open : undefined}
          onClick={() => setOpen(!open)}
          className={cn("flex h-9 w-6 shrink-0 items-center justify-center rounded", !hasChildren && "invisible")}
        >
          <ChevronRight className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-90")} />
        </button>
        <button type="button" aria-current={selected ? "true" : undefined} title={node.name} onClick={() => onSelect(node)} className="flex min-h-10 min-w-0 flex-1 items-center gap-2 rounded text-left">
          {selected ? <FolderOpen className="h-4 w-4 shrink-0" /> : <Folder className="h-4 w-4 shrink-0" />}
          <span className="min-w-0 break-words">{node.name}</span>
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger aria-label={`Thao tác với thư mục ${node.name}`} className="flex h-9 w-9 shrink-0 items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground">
            <MoreVertical aria-hidden="true" className="h-4 w-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onCreateChild(node)}>
              <Plus className="h-3.5 w-3.5" /> Thư mục con
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onRename(node)}>
              <Pencil className="h-3.5 w-3.5" /> Đổi tên / môn học
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onDelete(node)} className="text-destructive">
              <Trash2 className="h-3.5 w-3.5" /> Xoá
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {open && hasChildren && (
        <div role="group" aria-label={`Thư mục con của ${node.name}`}>
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              onSelect={onSelect}
              onCreateChild={onCreateChild}
              onRename={onRename}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function FolderTree(props: FolderTreeProps) {
  if (props.nodes.length === 0) {
    return <p className="px-2 py-6 text-center text-sm text-muted-foreground">Chưa có thư mục nào.</p>;
  }
  return (
    <div>
      {props.nodes.map((node) => (
        <TreeNode key={node.id} node={node} depth={0} {...props} />
      ))}
    </div>
  );
}
