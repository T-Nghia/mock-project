"use client";

import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Folder } from "@/lib/types";

interface FolderFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: "create" | "edit";
  parentName?: string | null;
  initial?: Folder | null;
  onSubmit: (data: { name: string; subject: string | null }) => Promise<void>;
}

export function FolderFormDialog({ open, onOpenChange, mode, parentName, initial, onSubmit }: FolderFormDialogProps) {
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      setName(initial?.name ?? "");
      setSubject(initial?.subject ?? "");
    }
  }, [open, initial]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await onSubmit({ name: name.trim(), subject: subject.trim() || null });
      onOpenChange(false);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "Tạo thư mục mới" : "Chỉnh sửa thư mục"}</DialogTitle>
          {parentName && <p className="text-sm text-muted-foreground">Trong: {parentName}</p>}
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="folder-name">Tên thư mục</Label>
            <Input id="folder-name" required value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="folder-subject">Môn học (tuỳ chọn)</Label>
            <Input
              id="folder-subject"
              placeholder="VD: Toán, Ngữ văn..."
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Huỷ
            </Button>
            <Button type="submit" loading={loading}>
              {mode === "create" ? "Tạo thư mục" : "Lưu thay đổi"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
