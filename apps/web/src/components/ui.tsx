import type { ReactNode } from "react";

// Small hand-rolled UI kit in the Jacaranda brand palette
// (packages/presentation/design-tokens.json: #563F7C / #34234F / #B7A3CB / #F7F5FA).

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section
      className={`rounded-xl border border-[#B7A3CB]/40 bg-white/90 p-5 shadow-sm ${className}`}
    >
      {children}
    </section>
  );
}

export function CardTitle({ children }: { children: ReactNode }) {
  return <h2 className="mb-3 text-lg font-semibold text-[#34234F]">{children}</h2>;
}

export function Button({
  children,
  disabled,
  onClick,
  type = "button",
  variant = "primary",
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
  variant?: "primary" | "secondary" | "danger";
}) {
  const styles = {
    primary: "bg-[#563F7C] text-white hover:bg-[#34234F]",
    secondary: "border border-[#563F7C] text-[#563F7C] hover:bg-[#F7F5FA]",
    danger: "bg-red-700 text-white hover:bg-red-800",
  }[variant];
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={`rounded-lg px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles}`}
    >
      {children}
    </button>
  );
}

const BADGE_STYLES: Record<string, string> = {
  queued: "bg-amber-100 text-amber-900",
  running: "bg-blue-100 text-blue-900",
  started: "bg-blue-100 text-blue-900",
  parsing: "bg-blue-100 text-blue-900",
  succeeded: "bg-green-100 text-green-900",
  completed: "bg-green-100 text-green-900",
  cached: "bg-green-50 text-green-800",
  parsed: "bg-green-100 text-green-900",
  stored: "bg-slate-100 text-slate-700",
  failed: "bg-red-100 text-red-900",
  draft: "bg-amber-100 text-amber-900",
  verified: "bg-green-100 text-green-900",
  approved: "bg-[#563F7C] text-white",
  rejected: "bg-red-100 text-red-900",
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const style = BADGE_STYLES[status] ?? "bg-slate-100 text-slate-700";
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>
      {label ?? status}
    </span>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-lg border border-dashed border-[#B7A3CB] bg-[#F7F5FA] px-4 py-6 text-center text-sm text-[#563F7C]">
      {children}
    </p>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
      {children}
    </p>
  );
}
