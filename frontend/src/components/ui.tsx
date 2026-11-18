import { Disc3, Loader2, Music4, X } from "lucide-react";
import {
  useEffect,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { createPortal } from "react-dom";
import { cn } from "../lib/utils";

/* ------------------------------------------------------------------ */
/* Button                                                              */
/* ------------------------------------------------------------------ */

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "outline";
type ButtonSize = "sm" | "md" | "lg" | "icon";

const buttonVariants: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-white shadow-[0_8px_24px_-12px_var(--accent)] hover:brightness-110 active:brightness-95",
  secondary: "bg-surface-2 text-fg hover:bg-surface-3",
  ghost: "bg-transparent text-muted hover:bg-surface-2 hover:text-fg",
  danger: "bg-danger-soft text-danger hover:bg-danger hover:text-white",
  outline: "border border-line bg-transparent text-fg hover:bg-surface-2",
};

const buttonSizes: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-xs gap-1.5 rounded-lg",
  md: "h-10 px-4 text-sm gap-2 rounded-xl",
  lg: "h-11 px-5 text-sm gap-2 rounded-xl",
  icon: "h-9 w-9 rounded-lg",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  loading,
  icon,
  className,
  children,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex select-none items-center justify-center font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:pointer-events-none disabled:opacity-50",
        buttonVariants[variant],
        buttonSizes[size],
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Surfaces                                                            */
/* ------------------------------------------------------------------ */

export function Card({
  className,
  children,
  ...props
}: { className?: string; children?: ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "min-w-0 rounded-2xl border border-line bg-surface/90 shadow-[0_1px_0_0_rgba(255,255,255,0.03)_inset]",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function SectionTitle({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-4 flex min-w-0 items-end justify-between gap-4">
      <div className="min-w-0">
        <h2 className="text-sm font-semibold tracking-wide text-fg">{title}</h2>
        {description && <p className="mt-1 text-xs text-muted">{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Badges and pills                                                    */
/* ------------------------------------------------------------------ */

type Tone = "neutral" | "accent" | "success" | "warning" | "danger";

const toneClasses: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted",
  accent: "bg-accent-soft text-accent",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
};

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
        toneClasses[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-md bg-surface-2 px-1.5 py-0.5 text-[11px] text-muted">{children}</span>
  );
}

/* ------------------------------------------------------------------ */
/* Form controls                                                       */
/* ------------------------------------------------------------------ */

export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("block", className)}>
      <span className="mb-1.5 flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-fg">{label}</span>
        {hint && <span className="text-[11px] text-muted">{hint}</span>}
      </span>
      {children}
      {error && <span className="mt-1 block text-[11px] text-danger">{error}</span>}
    </label>
  );
}

const inputClasses =
  "w-full rounded-xl border border-line bg-surface-2/60 px-3 py-2 text-sm text-fg placeholder:text-muted/70 focus:border-accent/60 focus:outline-none focus:ring-2 focus:ring-accent/20 disabled:opacity-50";

export function TextInput({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(inputClasses, "h-10", className)} {...props} />;
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(inputClasses, "min-h-[88px]", className)} {...props} />;
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn(inputClasses, "h-10 appearance-none pr-8", className)} {...props}>
      {children}
    </select>
  );
}

export function Switch({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-6 py-2">
      <div className="min-w-0">
        <p className="text-sm font-medium text-fg">{label}</p>
        {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative mt-0.5 h-6 w-11 shrink-0 rounded-full p-0 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:opacity-50",
          checked ? "bg-accent" : "bg-surface-3",
        )}
      >
        <span
          className={cn(
            "absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform duration-200",
            checked ? "translate-x-5" : "translate-x-0",
          )}
        />
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Modal                                                               */
/* ------------------------------------------------------------------ */

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  size?: "md" | "lg" | "xl";
}) {
  useEffect(() => {
    if (!open) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", handler);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handler);
    };
  }, [open, onClose]);

  if (!open) return null;

  const widths = { md: "max-w-lg", lg: "max-w-2xl", xl: "max-w-4xl" };

  return createPortal(
    <div className="fixed inset-0 z-[60] flex items-center justify-center overflow-y-auto overscroll-contain bg-black/50 p-3 backdrop-blur-sm sm:p-6">
      <div
        className={cn(
          "animate-in flex max-h-full w-full flex-col rounded-2xl border border-line bg-surface shadow-[var(--shadow)]",
          widths[size],
        )}
        role="dialog"
        aria-modal="true"
      >
          <div className="flex shrink-0 items-start justify-between gap-4 border-b border-line px-5 py-4">
            <div className="min-w-0">
              <h2 className="truncate text-base font-semibold text-fg">{title}</h2>
              {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
            </div>
            <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close">
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4">{children}</div>
          {footer && (
            <div className="flex shrink-0 items-center justify-end gap-2 border-t border-line px-5 py-3">
              {footer}
            </div>
          )}
      </div>
    </div>,
    document.body,
  );
}

/* ------------------------------------------------------------------ */
/* Feedback                                                            */
/* ------------------------------------------------------------------ */

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-4 w-4 animate-spin text-muted", className)} />;
}

export function ProgressBar({
  value,
  tone = "accent",
  className,
}: {
  value: number;
  tone?: "accent" | "success" | "warning" | "danger";
  className?: string;
}) {
  const colors = {
    accent: "bg-accent",
    success: "bg-success",
    warning: "bg-warning",
    danger: "bg-danger",
  };
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-surface-3", className)}>
      <div
        className={cn("h-full rounded-full transition-all", colors[tone])}
        style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }}
      />
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("shimmer rounded-lg", className)} />;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-14 text-center", className)}>
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-surface-2 text-muted">
        {icon ?? <Music4 className="h-5 w-5" />}
      </div>
      <p className="text-sm font-medium text-fg">{title}</p>
      {description && <p className="mt-1 max-w-sm text-xs text-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Cover art                                                           */
/* ------------------------------------------------------------------ */

const gradients = [
  "from-violet-500/70 to-fuchsia-500/40",
  "from-cyan-500/60 to-blue-600/40",
  "from-emerald-500/60 to-teal-600/40",
  "from-amber-500/60 to-orange-600/40",
  "from-rose-500/60 to-pink-600/40",
  "from-indigo-500/60 to-purple-600/40",
];

export function Cover({
  src,
  alt,
  className,
  rounded = "rounded-xl",
}: {
  src?: string | null;
  alt: string;
  className?: string;
  rounded?: string;
}) {
  const seed = Array.from(alt).reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const gradient = gradients[seed % gradients.length];

  return (
    <div
      className={cn(
        "relative overflow-hidden bg-surface-2",
        rounded,
        className,
      )}
    >
      <div className={cn("absolute inset-0 bg-gradient-to-br opacity-70", gradient)} />
      <div className="absolute inset-0 flex items-center justify-center text-white/70">
        <Disc3 className="h-1/3 w-1/3" strokeWidth={1.2} />
      </div>
      {src && (
        <img
          src={src}
          alt={alt}
          loading="lazy"
          className="relative h-full w-full object-cover"
          onError={(event) => {
            event.currentTarget.style.display = "none";
          }}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Page header                                                         */
/* ------------------------------------------------------------------ */

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-fg">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string; count?: number }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="inline-flex items-center gap-1 rounded-xl border border-line bg-surface-2/60 p-1">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={cn(
            "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
            value === option.value
              ? "bg-surface text-fg shadow-sm"
              : "text-muted hover:text-fg",
          )}
        >
          {option.label}
          {option.count !== undefined && (
            <span className="rounded-full bg-surface-3 px-1.5 text-[10px] text-muted">{option.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

export function KeyValue({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <span className="text-xs text-muted">{label}</span>
      <span className="text-right text-xs font-medium text-fg">{value}</span>
    </div>
  );
}
