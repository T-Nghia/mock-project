"use client";

import { useEffect, useRef, useState } from "react";
import { FormError, formError } from "@/components/auth/form-error";
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
  const [error, setError] = useState<string | null>(null);
  const lock = useRef(false);
  function close(value: boolean) { if (!lock.current) onOpenChange(value); }

  useEffect(() => {
    if (open) {
      setError(null);
      setName(initial?.name ?? "");
      setSubject(initial?.subject ?? "");
    }
  }, [open, initial]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (lock.current) return;
    if (!name.trim()) { setError("Vui lòng nhập tên thư mục."); return; }
    lock.current = true;
    setError(null);
    setLoading(true);
    try {
      await onSubmit({ name: name.trim(), subject: subject.trim() || null });
      onOpenChange(false);
    } catch (err) {
      setError(formError(err, "Không thể lưu thư mục. Vui lòng thử lại."));
    } finally {
      lock.current = false;
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent onClose={loading ? undefined : () => close(false)}>
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "Tạo thư mục mới" : "Chỉnh sửa thư mục"}</DialogTitle>
          {parentName && <p className="break-words text-sm text-muted-foreground">Trong: {parentName}. Thư mục con kế thừa môn học của thư mục cha.</p>}
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <FormError message={error} />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="folder-name">Tên thư mục</Label>
            <Input id="folder-name" required maxLength={255} disabled={loading} value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="folder-subject">Môn học (tuỳ chọn)</Label>
            <Input
              id="folder-subject"
              maxLength={255}
              disabled={loading}
              placeholder="VD: Toán, Ngữ văn..."
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" disabled={loading} onClick={() => close(false)}>
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
