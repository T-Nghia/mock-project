"use client";

import { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "./dialog";
import { Button } from "./button";
import { FormError, formError } from "@/components/auth/form-error";

export function ConfirmActionDialog({ open, onOpenChange, title, description, label, destructive = false, onConfirm }: {
  open: boolean; onOpenChange: (open: boolean) => void; title: string; description: string; label: string; destructive?: boolean; onConfirm: () => Promise<void>;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lock = useRef(false);
  useEffect(() => { if (open) setError(null); }, [open]);
  function close(value: boolean) { if (!lock.current) onOpenChange(value); }
  async function confirm() {
    if (lock.current) return;
    lock.current = true; setLoading(true); setError(null);
    try { await onConfirm(); onOpenChange(false); }
    catch (err) { setError(formError(err, "Không thể hoàn tất thao tác. Vui lòng thử lại.")); }
    finally { lock.current = false; setLoading(false); }
  }
  return <Dialog open={open} onOpenChange={close}><DialogContent><DialogHeader><DialogTitle>{title}</DialogTitle><DialogDescription className="break-words">{description}</DialogDescription></DialogHeader><FormError message={error} /><DialogFooter><Button autoFocus variant="outline" disabled={loading} onClick={() => close(false)}>Huỷ</Button><Button variant={destructive ? "destructive" : "default"} loading={loading} onClick={confirm}>{label}</Button></DialogFooter></DialogContent></Dialog>;
}
