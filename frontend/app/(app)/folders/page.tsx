"use client";

import { useCallback, useEffect, useState } from "react";
import { FileText, FolderPlus, MoveRight } from "lucide-react";
import { foldersApi } from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { Folder, FolderDocument, FolderTreeNode } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select } from "@/components/ui/select";
import { FolderTree } from "@/components/folders/folder-tree";
import { FolderFormDialog } from "@/components/folders/folder-form-dialog";
import { StatusBadge } from "@/components/documents/status-badge";
import { formatDate } from "@/lib/utils";
import { useToast } from "@/lib/toast-context";

function flatten(nodes: FolderTreeNode[]): FolderTreeNode[] {
  return nodes.flatMap((n) => [n, ...flatten(n.children)]);
}

export default function FoldersPage() {
  const { toast } = useToast();
  const [tree, setTree] = useState<FolderTreeNode[]>([]);
  const [loadingTree, setLoadingTree] = useState(true);
  const [selected, setSelected] = useState<FolderTreeNode | null>(null);
  const [docs, setDocs] = useState<FolderDocument[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogMode, setDialogMode] = useState<"create" | "edit">("create");
  const [dialogParent, setDialogParent] = useState<FolderTreeNode | null>(null);
  const [dialogInitial, setDialogInitial] = useState<Folder | null>(null);

  const loadTree = useCallback(async () => {
    setLoadingTree(true);
    try {
      const data = await foldersApi.tree();
      setTree(data);
    } catch (err) {
      toast({ title: "Không tải được thư mục", description: err instanceof ApiError ? err.message : undefined, variant: "error" });
    } finally {
      setLoadingTree(false);
    }
  }, [toast]);

  useEffect(() => {
    loadTree();
  }, [loadTree]);

  const loadDocs = useCallback(
    async (folderId: string) => {
      setLoadingDocs(true);
      try {
        const data = await foldersApi.documents(folderId, false);
        setDocs(data);
      } catch (err) {
        toast({ title: "Không tải được tài liệu", description: err instanceof ApiError ? err.message : undefined, variant: "error" });
      } finally {
        setLoadingDocs(false);
      }
    },
    [toast]
  );

  useEffect(() => {
    if (selected) loadDocs(selected.id);
    else setDocs([]);
  }, [selected, loadDocs]);

  function openCreate(parent: FolderTreeNode | null) {
    setDialogMode("create");
    setDialogParent(parent);
    setDialogInitial(null);
    setDialogOpen(true);
  }

  function openEdit(node: FolderTreeNode) {
    setDialogMode("edit");
    setDialogParent(null);
    setDialogInitial(node);
    setDialogOpen(true);
  }

  async function handleSubmit(data: { name: string; subject: string | null }) {
    try {
      if (dialogMode === "create") {
        await foldersApi.create({ name: data.name, subject: data.subject, parent_folder_id: dialogParent?.id ?? null });
        toast({ title: "Đã tạo thư mục", variant: "success" });
      } else if (dialogInitial) {
        await foldersApi.update(dialogInitial.id, { name: data.name, subject: data.subject });
        toast({ title: "Đã cập nhật thư mục", variant: "success" });
      }
      await loadTree();
    } catch (err) {
      toast({ title: "Thao tác thất bại", description: err instanceof ApiError ? err.message : undefined, variant: "error" });
    }
  }

  async function handleDelete(node: FolderTreeNode) {
    if (!confirm(`Xoá thư mục "${node.name}" và toàn bộ thư mục con? Tài liệu bên trong sẽ được giữ lại.`)) return;
    try {
      await foldersApi.remove(node.id);
      toast({ title: "Đã xoá thư mục", variant: "success" });
      if (selected?.id === node.id) setSelected(null);
      await loadTree();
    } catch (err) {
      toast({ title: "Xoá thất bại", description: err instanceof ApiError ? err.message : undefined, variant: "error" });
    }
  }

  async function handleMove(documentId: string, folderId: string) {
    try {
      await foldersApi.moveDocument(documentId, folderId || null);
      toast({ title: "Đã chuyển tài liệu", variant: "success" });
      if (selected) loadDocs(selected.id);
    } catch (err) {
      toast({ title: "Chuyển thất bại", description: err instanceof ApiError ? err.message : undefined, variant: "error" });
    }
  }

  const allFolders = flatten(tree);

  return (
    <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
      <Card className="h-fit">
        <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
          <CardTitle className="text-sm">Cây thư mục</CardTitle>
          <Button size="sm" variant="ghost" onClick={() => openCreate(null)}>
            <FolderPlus className="h-4 w-4" />
          </Button>
        </CardHeader>
        <CardContent className="p-2 pt-0">
          {loadingTree ? (
            <div className="flex flex-col gap-2 p-2">
              <Skeleton className="h-6" />
              <Skeleton className="h-6" />
              <Skeleton className="h-6" />
            </div>
          ) : (
            <FolderTree
              nodes={tree}
              selectedId={selected?.id ?? null}
              onSelect={setSelected}
              onCreateChild={openCreate}
              onRename={openEdit}
              onDelete={handleDelete}
            />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{selected ? selected.name : "Chọn một thư mục"}</CardTitle>
          {selected?.subject && <p className="text-sm text-muted-foreground">Môn học: {selected.subject}</p>}
        </CardHeader>
        <CardContent>
          {!selected ? (
            <p className="py-10 text-center text-sm text-muted-foreground">
              Chọn một thư mục bên trái để xem tài liệu bên trong.
            </p>
          ) : loadingDocs ? (
            <div className="flex flex-col gap-2">
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
            </div>
          ) : docs.length === 0 ? (
            <p className="py-10 text-center text-sm text-muted-foreground">Thư mục này chưa có tài liệu.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tên tài liệu</TableHead>
                  <TableHead>Trạng thái</TableHead>
                  <TableHead>Ngày tạo</TableHead>
                  <TableHead className="w-56">Chuyển tới</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {docs.map((doc) => (
                  <TableRow key={doc.id}>
                    <TableCell className="flex items-center gap-2 font-medium">
                      <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <a href={`/documents/${doc.id}`} className="hover:underline">
                        {doc.title}
                      </a>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={doc.processing_status} />
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{formatDate(doc.created_at)}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Select
                          defaultValue={selected.id}
                          onChange={(e) => handleMove(doc.id, e.target.value)}
                          className="h-8 text-xs"
                        >
                          <option value="">— Ngoài thư mục —</option>
                          {allFolders.map((f) => (
                            <option key={f.id} value={f.id}>
                              {f.name}
                            </option>
                          ))}
                        </Select>
                        <MoveRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <FolderFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        mode={dialogMode}
        parentName={dialogParent?.name}
        initial={dialogInitial}
        onSubmit={handleSubmit}
      />
    </div>
  );
}
