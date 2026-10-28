import { ApiError } from "@/lib/api";

// Keep server diagnostics out of public forms.
export function formError(error: unknown, fallback: string) {
  return error instanceof ApiError && error.status < 500 ? error.message : fallback;
}
export function FormError({ message }: { message: string | null }) {
  return message ? <p role="alert" className="break-words rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-sm leading-6 text-destructive">{message}</p> : null;
}
