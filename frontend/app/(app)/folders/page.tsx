"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { FolderPlus, FileText, FolderOpen } from "lucide-react";
import { foldersApi } from "@/lib/api";
import type { Folder, FolderDocument, FolderTreeNode } from "@/lib/types";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/lib/toast-context";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { PageLoading, PageState } from "@/components/ui/page-state";
import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";
import { FolderTree } from "@/components/folders/folder-tree";
import { FolderFormDialog } from "@/components/folders/folder-form-dialog";
import { StatusBadge } from "@/components/documents/status-badge";
import { formatDate } from "@/lib/utils";

function flatten(nodes: FolderTreeNode[]): FolderTreeNode[] {
  return nodes.flatMap((node) => [node, ...flatten(node.children)]);
}
export default function FoldersPage() {
  const { user } = useAuth();
  // Presentation follows the endpoint's teacher-only contract; auth guards stay unchanged.
  if (user?.role !== "teacher") return <PageState title="Thư mục dành cho giáo viên" description="Tài khoản của bạn không có quyền quản lý thư mục. Bạn vẫn có thể khám phá tài liệu trong thư viện."><Link href="/search" className={buttonVariants()}>Mở thư viện</Link></PageState>;
  return <FolderManager />;
}
function FolderManager() {
  const { toast } = useToast();
  const [tree, setTree] = useState<FolderTreeNode[]>([]);
  const [loadingTree, setLoadingTree] = useState(true);
  const [treeError, setTreeError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<{ id: string; items: FolderDocument[] } | null>(null);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [docsError, setDocsError] = useState(false);
  const [docsAttempt, setDocsAttempt] = useState(0);
  const [moving, setMoving] = useState<string | null>(null);
  const moveLock = useRef(false);
  const treeRequest = useRef(0);
  const [deleteTarget, setDeleteTarget] = useState<FolderTreeNode | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [mode, setMode] = useState<"create" | "edit">("create");
  const [parent, setParent] = useState<FolderTreeNode | null>(null);
  const [initial, setInitial] = useState<Folder | null>(null);
  const allFolders = flatten(tree);
  const selected = allFolders.find((node) => node.id === selectedId);

  const loadTree = useCallback(async () => {
    const ticket = ++treeRequest.current;
    setLoadingTree(true); setTreeError(false);
    try {
      const data = await foldersApi.tree();
      if (ticket !== treeRequest.current) return;
      setTree(data);
      setSelectedId((id) => flatten(data).some((node) => node.id === id) ? id : null);
    } catch { if (ticket === treeRequest.current) setTreeError(true); }
    finally { if (ticket === treeRequest.current) setLoadingTree(false); }
  }, []);
  useEffect(() => { void loadTree(); return () => { treeRequest.current += 1; }; }, [loadTree]);
  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    setLoadingDocs(true); setDocsError(false);
    foldersApi.documents(selectedId, false)
      .then((items) => { if (!cancelled) setDocuments({ id: selectedId, items }); })
      .catch(() => { if (!cancelled) setDocsError(true); })
      .finally(() => { if (!cancelled) setLoadingDocs(false); });
    return () => { cancelled = true; };
  }, [selectedId, docsAttempt]);
  function create(node: FolderTreeNode | null) { setMode("create"); setParent(node); setInitial(null); setDialogOpen(true); }
  function edit(node: FolderTreeNode) { setMode("edit"); setParent(null); setInitial(node); setDialogOpen(true); }
  async function save(data: { name: string; subject: string | null }) {
    if (mode === "create") await foldersApi.create({ ...data, parent_folder_id: parent?.id ?? null });
    else if (initial) await foldersApi.update(initial.id, data);
    toast({ title: mode === "create" ? "Đã tạo thư mục" : "Đã cập nhật thư mục", variant: "success" });
    await loadTree();
  }
  async function remove() {
    if (!deleteTarget) return;
    await foldersApi.remove(deleteTarget.id);
    const removed = new Set(flatten([deleteTarget]).map((node) => node.id));
    if (selectedId && removed.has(selectedId)) setSelectedId(null);
    // Prune only after server confirmation; a refresh failure must not resurrect a deleted node.
    const prune = (nodes: FolderTreeNode[]): FolderTreeNode[] => nodes.filter((node) => !removed.has(node.id)).map((node) => ({ ...node, children: prune(node.children) }));
    setTree((previous) => prune(previous));
    toast({ title: "Đã xoá thư mục", variant: "success" });
    await loadTree();
  }
  async function move(documentId: string, destination: string) {
    if (moveLock.current || destination === selectedId) return;
    moveLock.current = true; setMoving(documentId);
    try {
      await foldersApi.moveDocument(documentId, destination || null);
      setDocuments((previous) => previous ? { ...previous, items: previous.items.filter((doc) => doc.id !== documentId) } : previous);
      toast({ title: "Đã chuyển tài liệu", variant: "success" });
    } catch { toast({ title: "Chuyển thất bại", description: "Tài liệu vẫn ở thư mục hiện tại. Vui lòng thử lại.", variant: "error" }); }
    finally { moveLock.current = false; setMoving(null); }
  }
  const docs = documents?.id === selectedId ? documents.items : [];
  return <div className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="mb-2 text-xs uppercase tracking-widest text-muted-foreground">Sắp xếp kiến thức</p><h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Thư mục của bạn</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">Tổ chức tài liệu theo môn học và những chủ đề bạn quan tâm.</p></div><Button onClick={() => create(null)}><FolderPlus aria-hidden="true" className="h-4 w-4" />Tạo thư mục</Button></header>
    <div className="grid min-w-0 items-start gap-5 xl:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
      <Card className="min-w-0 p-3"><div className="flex items-center gap-2 border-b border-border px-2 pb-3"><FolderOpen aria-hidden="true" className="h-4 w-4 text-primary" /><h3 className="text-sm font-semibold">Cây thư mục</h3><span className="ml-auto text-xs text-muted-foreground">{allFolders.length}</span></div><div className="mt-3">{loadingTree && !tree.length ? <PageLoading label="Đang tải thư mục" /> : <>{treeError && <PageState title="Không tải được thư mục" description="Danh sách trước đó được giữ lại nếu có." retry={() => void loadTree()} />}{!treeError && !tree.length ? <PageState title="Chưa có thư mục nào" description="Tạo thư mục đầu tiên để bắt đầu sắp xếp tài liệu."><Button variant="outline" onClick={() => create(null)}>Tạo thư mục đầu tiên</Button></PageState> : <FolderTree nodes={tree} selectedId={selectedId} onSelect={(node) => setSelectedId(node.id)} onCreateChild={create} onRename={edit} onDelete={setDeleteTarget} />}{loadingTree && <p role="status" className="p-2 text-xs text-muted-foreground">Đang cập nhật thư mục…</p>}</>}</div></Card>
      <section aria-label="Tài liệu trong thư mục" className="min-w-0 space-y-4">
        {!selected ? <PageState title="Chọn một thư mục" description="Chọn thư mục trong cây để xem và sắp xếp tài liệu bên trong." /> : <>
          <div className="rounded-xl border border-border bg-card p-5"><h3 className="break-words text-lg font-semibold">{selected.name}</h3>{selected.subject && <p className="mt-1 break-words text-sm text-muted-foreground">Môn học: {selected.subject}</p>}<p className="mt-3 text-xs leading-5 text-muted-foreground">Tài liệu trực tiếp trong thư mục này. Chọn thư mục con để xem nội dung của thư mục con.</p></div>
          {loadingDocs || (!docsError && documents?.id !== selectedId) ? <PageLoading label="Đang tải tài liệu trong thư mục" /> : docsError ? <PageState title="Không tải được tài liệu" description="Vui lòng thử lại. Không có tài liệu nào bị thay đổi." retry={() => setDocsAttempt((v) => v + 1)} /> : !docs.length ? <PageState title="Thư mục này chưa có tài liệu" description="Bạn có thể chọn thư mục này khi tải tài liệu lên."><Link href="/documents/upload" className={buttonVariants({ variant: "outline" })}>Tải tài liệu lên</Link></PageState> : <ul className="space-y-3">{docs.map((doc) => <li key={doc.id} className="min-w-0 rounded-xl border border-border bg-card p-4 sm:p-5"><div className="flex gap-3"><FileText aria-hidden="true" className="mt-1 h-5 w-5 shrink-0 text-primary" /><div className="min-w-0 flex-1"><Link href={`/documents/${doc.id}`} className="break-words font-semibold hover:text-primary hover:underline">{doc.title}</Link><div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground"><span>{doc.file_type.toUpperCase()}</span><span>{formatDate(doc.created_at)}</span><StatusBadge status={doc.processing_status} /></div><div className="mt-4 space-y-2"><label htmlFor={`move-${doc.id}`} className="text-xs text-muted-foreground">Chuyển tài liệu tới</label><Select id={`move-${doc.id}`} value={selected.id} disabled={!!moving} onChange={(event) => void move(doc.id, event.target.value)}><option value="">Ngoài thư mục</option>{allFolders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</Select>{moving === doc.id && <p role="status" className="text-xs text-muted-foreground">Đang chuyển tài liệu…</p>}</div></div></div></li>)}</ul>}
        </>}
      </section>
    </div>
    <FolderFormDialog open={dialogOpen} onOpenChange={setDialogOpen} mode={mode} parentName={parent?.name} initial={initial} onSubmit={save} />
    <ConfirmActionDialog open={!!deleteTarget} onOpenChange={(open) => { if (!open) setDeleteTarget(null); }} title="Xoá thư mục?" description={`Thư mục “${deleteTarget?.name ?? ""}” và toàn bộ thư mục con sẽ bị xoá. Tài liệu bên trong được giữ lại và đưa ra ngoài thư mục.`} label="Xoá thư mục" destructive onConfirm={remove} />
  </div>;
}
