"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { documentsApi, ApiError } from "@/lib/api";

interface DeleteDocumentButtonProps {
  documentId: string;
  documentTitle: string;
  onDeleted: () => void;
}

export function DeleteDocumentButton({ documentId, documentTitle, onDeleted }: DeleteDocumentButtonProps) {
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConfirm() {
    setDeleting(true);
    setError(null);
    try {
      await documentsApi.remove(documentId);
      setOpen(false);
      onDeleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không thể xóa tài liệu. Vui lòng thử lại.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <Button variant="outline" size="sm" className="text-destructive hover:text-destructive" onClick={() => setOpen(true)}>
        <Trash2 className="h-4 w-4" /> Xóa
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent onClose={() => setOpen(false)}>
          <DialogHeader>
            <DialogTitle>Xóa tài liệu?</DialogTitle>
            <DialogDescription>
              Bạn sắp xóa <span className="font-medium text-foreground">&ldquo;{documentTitle}&rdquo;</span>. Hành
              động này không thể hoàn tác — tài liệu, các cuộc trò chuyện AI, bình luận và đánh giá liên quan sẽ bị
              xóa vĩnh viễn.
            </DialogDescription>
          </DialogHeader>

          {error && (
            <Alert variant="destructive" className="mb-2">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={deleting}>
              Hủy
            </Button>
            <Button variant="destructive" onClick={handleConfirm} loading={deleting}>
              Xóa vĩnh viễn
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
