import Link from "next/link";
import { BookOpen, GraduationCap, MessageSquareText } from "lucide-react";

export function AuthFrame({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <main className="min-h-dvh p-4 sm:p-8 lg:flex lg:items-center lg:justify-center">
      <div className="mx-auto grid w-full max-w-5xl overflow-hidden rounded-2xl border border-border bg-card shadow-sm lg:grid-cols-2">
        <aside className="flex flex-col justify-between gap-10 border-b border-border bg-sidebar p-6 sm:p-10 lg:border-b-0 lg:border-r">
          <Link href="/" aria-label="SLRMS — Trang chủ" className="flex w-fit items-center gap-3 rounded-md">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground"><GraduationCap aria-hidden="true" className="h-6 w-6" /></span>
            <span><span className="block font-bold tracking-tight">SLRMS</span><span className="text-xs text-muted-foreground">Không gian học tập thông minh</span></span>
          </Link>
          <div className="hidden lg:block">
            <p className="text-xs font-medium uppercase tracking-widest text-primary">Đọc. Khám phá. Kết nối.</p>
            <h2 className="mt-4 text-3xl font-semibold leading-tight tracking-tight">Tài liệu của bạn.<br />Những góc nhìn mới.</h2>
            <p className="mt-4 max-w-sm leading-7 text-muted-foreground">Một không gian để tìm tài nguyên, sắp xếp kiến thức và học cùng trợ lý AI.</p>
            <div className="mt-8 space-y-4 text-sm"><p className="flex items-center gap-3"><BookOpen aria-hidden="true" className="h-5 w-5 text-primary" />Tài nguyên học tập trong tầm tay</p><p className="flex items-center gap-3"><MessageSquareText aria-hidden="true" className="h-5 w-5 text-primary" />Hỏi và khám phá từ tài liệu</p></div>
          </div>
          <p className="hidden text-xs text-muted-foreground lg:block">Smart Learning Resource Management System</p>
        </aside>
        <section aria-labelledby="auth-title" className="min-w-0 px-5 py-8 sm:p-10">
          <h1 id="auth-title" className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="mb-7 mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
          {children}
        </section>
      </div>
    </main>
  );
}
