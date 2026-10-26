/** Small component kit in the style of shadcn/ui, kept in the repository. */
import clsx from "clsx";
import { ArrowDown, ArrowUp, Loader2, X } from "lucide-react";
import {
  forwardRef,
  useEffect,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import { num } from "../../lib/format";

export { clsx as cn };

type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline";
const variants: Record<Variant, string> = {
  primary: "bg-oak-600 text-white hover:bg-oak-500 disabled:bg-oak-700/50",
  secondary: "bg-surface-3 text-ink hover:brightness-110 border border-line",
  ghost: "text-muted hover:text-ink hover:bg-surface-3",
  danger: "bg-red-600 text-white hover:bg-red-500",
  outline: "border border-line text-ink hover:bg-surface-3",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "sm" | "md";
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading, icon, className, children, disabled, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition disabled:cursor-not-allowed disabled:opacity-60",
        size === "sm" ? "h-8 px-3 text-xs" : "h-9 px-4 text-sm",
        variants[variant],
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </button>
  );
});

export function Card({ className, children, title, actions }: { className?: string; children: ReactNode; title?: ReactNode; actions?: ReactNode }) {
  return (
    <section className={clsx("rounded-xl border border-line bg-surface shadow-sm", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
          {title && <h2 className="text-sm font-semibold">{title}</h2>}
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Badge({ children, className, color, title }: { children: ReactNode; className?: string; color?: string; title?: string }) {
  return (
    <span
      title={title}
      style={color ? { backgroundColor: `${color}33`, color, borderColor: `${color}66` } : undefined}
      className={clsx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium",
        !color && "border-line bg-surface-3 text-ink",
        className,
      )}
    >
      {children}
    </span>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...props }, ref) {
  return (
    <input
      ref={ref}
      className={clsx(
        "h-9 w-full rounded-lg border border-line bg-surface-2 px-3 text-sm text-ink placeholder:text-muted focus:border-oak-500 focus:outline-none",
        className,
      )}
      {...props}
    />
  );
});

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={clsx(
        "w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-oak-500 focus:outline-none",
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={clsx("h-9 rounded-lg border border-line bg-surface-2 px-2 text-sm text-ink focus:border-oak-500 focus:outline-none", className)}
      {...props}
    >
      {children}
    </select>
  );
}

export function Label({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="mb-1 block text-xs font-medium text-muted">
      {children}
      {hint && <span className="ml-1 font-normal opacity-80">{hint}</span>}
    </label>
  );
}

/** A labelled form control. The control sits inside the label so the two are linked for
 * screen readers; the hint stays outside the label so it does not become part of the name. */
export function Field({ label, hint, children }: { label: ReactNode; hint?: ReactNode; children: ReactNode }) {
  return (
    <div>
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-muted">{label}</span>
        {children}
      </label>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

export function Checkbox({ checked, onChange, label, disabled }: { checked: boolean; onChange: (value: boolean) => void; label?: ReactNode; disabled?: boolean }) {
  return (
    <label className={clsx("inline-flex items-center gap-2 text-sm", disabled ? "opacity-50" : "cursor-pointer")}>
      <input
        type="checkbox"
        className="h-4 w-4 rounded border-line accent-oak-500"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      {label}
    </label>
  );
}

export function Switch({ checked, onChange, label, description }: { checked: boolean; onChange: (value: boolean) => void; label: ReactNode; description?: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4 py-2">
      <span>
        <span className="block text-sm">{label}</span>
        {description && <span className="block text-xs text-muted">{description}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={clsx("relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition", checked ? "bg-oak-500" : "bg-surface-3 border border-line")}
      >
        <span className={clsx("absolute top-0.5 h-4 w-4 rounded-full bg-white transition", checked ? "left-4" : "left-0.5")} />
      </button>
    </label>
  );
}

export function Spinner({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 p-6 text-sm text-muted" role="status">
      <Loader2 className="h-4 w-4 animate-spin" /> {label ?? t("common.loading")}
    </div>
  );
}

export function EmptyState({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-line p-8 text-center">
      {icon && <div className="text-muted">{icon}</div>}
      <p className="font-medium">{title}</p>
      {children && <div className="max-w-xl text-sm text-muted">{children}</div>}
    </div>
  );
}

export function Alert({ tone = "info", title, children }: { tone?: "info" | "warning" | "error" | "success"; title?: ReactNode; children?: ReactNode }) {
  const tones = {
    info: "border-sky-500/40 bg-sky-500/10 text-sky-200 [.light_&]:text-sky-900",
    warning: "border-amber-500/40 bg-amber-500/10 text-amber-200",
    error: "border-red-500/40 bg-red-500/10 text-red-200",
    success: "border-oak-500/40 bg-oak-500/10 text-oak-300",
  };
  return (
    <div className={clsx("rounded-lg border px-4 py-3 text-sm", tones[tone])} role={tone === "error" ? "alert" : "status"}>
      {title && <p className="font-semibold">{title}</p>}
      {children && <div className={clsx(title && "mt-1", "opacity-90")}>{children}</div>}
    </div>
  );
}

/** Longer text values get a smaller font so they fit in a narrow card. */
const LONG_STAT = 8;

export function Stat({ label, value, hint, onClick, accent }: { label: string; value: ReactNode; hint?: ReactNode; onClick?: () => void; accent?: string }) {
  const Component = onClick ? "button" : "div";
  return (
    <Component
      onClick={onClick}
      className={clsx(
        "flex flex-col rounded-xl border border-line bg-surface p-4 text-left shadow-sm",
        onClick && "transition hover:border-oak-500/60 hover:bg-surface-3",
      )}
    >
      <span className="text-xs text-muted">{label}</span>
      <span
        className={clsx("mt-1 font-semibold tabular-nums", typeof value === "string" && value.length > LONG_STAT ? "text-lg leading-snug" : "text-2xl")}
        style={accent ? { color: accent } : undefined}
      >
        {value}
      </span>
      {hint && <span className="mt-1 text-xs text-muted">{hint}</span>}
    </Component>
  );
}

export function Tabs<T extends string>({ value, onChange, tabs }: { value: T; onChange: (value: T) => void; tabs: { value: T; label: ReactNode; count?: number }[] }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-line" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.value}
          role="tab"
          aria-selected={tab.value === value}
          onClick={() => onChange(tab.value)}
          className={clsx(
            "-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm",
            tab.value === value ? "border-oak-500 text-ink" : "border-transparent text-muted hover:text-ink",
          )}
        >
          {tab.label}
          {tab.count !== undefined && <span className="ml-1.5 rounded bg-surface-3 px-1.5 text-xs text-muted">{tab.count}</span>}
        </button>
      ))}
    </div>
  );
}

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  'input:not([disabled]):not([type="hidden"])',
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function focusableIn(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => !el.closest("[hidden], [inert]"));
}

/** Open dialogs, the topmost last. Only that one reacts to Escape and Tab. */
const openDialogs: symbol[] = [];

/**
 * The element that last had focus. A button that shows a spinner is disabled while it waits and
 * loses focus to the page, so by the time its dialog opens, document.activeElement is the body.
 */
let lastFocused: HTMLElement | null = null;
if (typeof document !== "undefined") {
  document.addEventListener("focusin", (event) => {
    if (event.target instanceof HTMLElement) lastFocused = event.target;
  });
}

/**
 * A modal dialog: named by its title, focus moves in on opening and returns to the button that
 * opened it, Tab and Shift+Tab stay inside, Escape closes, and the page behind it is inert.
 * Initial focus goes to an element marked `data-autofocus` or with `autoFocus`, otherwise to the
 * first control in the body. A footer action never gets focus on its own (audit A14).
 */
export function Dialog({ open, onClose, title, children, footer, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const { t } = useTranslation();
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  });

  useEffect(() => {
    if (!open) return;
    const token = Symbol("dialog");
    const active = document.activeElement;
    const previous = active instanceof HTMLElement && active !== document.body ? active : lastFocused;
    const root = document.getElementById("root");
    openDialogs.push(token);
    root?.setAttribute("inert", "");

    const node = panel.current;
    if (node && !node.contains(document.activeElement)) {
      const first = node.querySelector<HTMLElement>("[data-autofocus]") ?? (body.current ? focusableIn(body.current)[0] : undefined);
      (first ?? node).focus();
    }

    const onKey = (event: KeyboardEvent) => {
      const current = panel.current;
      if (openDialogs[openDialogs.length - 1] !== token || !current) return;
      if (event.key === "Escape") {
        event.preventDefault();
        close.current();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusableIn(current);
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (!first || !last) {
        event.preventDefault();
        current.focus();
      } else if (!current.contains(active)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && (active === first || active === current)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      openDialogs.splice(openDialogs.indexOf(token), 1);
      if (openDialogs.length === 0) root?.removeAttribute("inert");
      if (previous?.isConnected) previous.focus();
    };
  }, [open]);

  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4" onClick={onClose}>
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={clsx("max-h-[92vh] w-full overflow-auto rounded-t-2xl border border-line bg-surface shadow-xl outline-none sm:rounded-2xl", wide ? "sm:max-w-3xl" : "sm:max-w-lg")}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 id={titleId} className="font-semibold">
            {title}
          </h2>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label={t("common.close")} icon={<X className="h-4 w-4" />} />
        </header>
        <div ref={body} className="p-5">
          {children}
        </div>
        {footer && <footer className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</footer>}
      </div>
    </div>,
    document.body,
  );
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (page: number) => void }) {
  const { t } = useTranslation();
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex items-center justify-between gap-2 text-sm text-muted">
      <span>
        {total === 0 ? t("pagination.none") : t("pagination.range", { from: num((page - 1) * pageSize + 1), to: num(Math.min(page * pageSize, total)), total: num(total) })}
      </span>
      <div className="flex gap-1">
        <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          {t("common.previous")}
        </Button>
        <span className="px-2 py-1.5 text-xs">
          {page} / {pages}
        </span>
        <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          {t("common.next")}
        </Button>
      </div>
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function KeyValue({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1.5 text-sm">
      {items.map(([key, value], index) => (
        <div key={index} className="contents">
          <dt className="text-muted">{key}</dt>
          <dd className="text-right tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * Column header that sorts on click. `sort` is the current value, with '-' for descending.
 * The first click sorts descending, or ascending for columns where low is best, such as a rank.
 */
export function SortHeader({
  label,
  sortKey,
  sort,
  onSort,
  ascendingFirst = false,
}: {
  label: string;
  sortKey: string;
  sort: string;
  onSort: (value: string) => void;
  ascendingFirst?: boolean;
}) {
  const active = sort.replace("-", "") === sortKey;
  const descending = sort.startsWith("-");
  const first = ascendingFirst ? sortKey : `-${sortKey}`;
  const second = ascendingFirst ? `-${sortKey}` : sortKey;
  return (
    <button type="button" className="inline-flex items-center gap-1 hover:text-ink" onClick={() => onSort(active && sort === first ? second : first)}>
      {label}
      {active && (descending ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />)}
    </button>
  );
}
