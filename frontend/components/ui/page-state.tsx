import { AlertCircle, Inbox } from "lucide-react";
import { Button } from "./button";
import { Skeleton } from "./skeleton";

export function PageLoading({ label }: { label: string }) {
  return <div role="status" aria-label={label} className="space-y-3"><span className="sr-only">{label}</span>{[0, 1, 2].map((n) => <Skeleton key={n} className="h-28 rounded-xl" />)}</div>;
}

export function PageState({ title, description, retry, children }: { title: string; description: string; retry?: () => void; children?: React.ReactNode }) {
  const Icon = retry ? AlertCircle : Inbox;
  return <div className="flex min-h-56 flex-col items-center justify-center gap-4 rounded-xl border border-border bg-card p-6 text-center">
    <Icon aria-hidden="true" className="h-8 w-8 text-muted-foreground" />
    <div role={retry ? "alert" : undefined}><h3 className="font-semibold">{title}</h3><p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">{description}</p></div>
    {retry && <Button variant="outline" onClick={retry}>Thử lại</Button>}{children}
  </div>;
}
