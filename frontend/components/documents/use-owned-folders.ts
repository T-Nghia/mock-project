"use client";

import { useEffect, useState } from "react";
import { foldersApi } from "@/lib/api";
import type { Folder } from "@/lib/types";

// /folders uses require_role("teacher"), not the broader document-upload permission.
export function useOwnedFolders(teacherId?: string) {
  const [folders, setFolders] = useState<Folder[]>([]);
  const [loading, setLoading] = useState(!!teacherId);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!teacherId) return;
    let cancelled = false;
    setLoading(true);
    setError(false);
    foldersApi.list()
      .then((items) => { if (!cancelled) setFolders(items); })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [teacherId, attempt]);
  return { folders, loading, error, retry: () => setAttempt((value) => value + 1) };
}
