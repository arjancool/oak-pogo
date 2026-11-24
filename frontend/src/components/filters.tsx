import clsx from "clsx";
import { Filter } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button, Card } from "./ui";

/**
 * The filter button and panel that pages share, so filtering looks and works the same everywhere:
 * one button with the number of active filters, a panel with the choices below the toolbar, and
 * a button to clear them. The choices themselves stay in the URL of the page.
 */

/** Whether the panel is open. It starts open when the page opens with filters already set. */
export function useFilterPanel(active: number): [boolean, () => void] {
  const [open, setOpen] = useState(active > 0);
  return [open, () => setOpen((value) => !value)];
}

export function FilterButton({
  open,
  onToggle,
  active,
  onClear,
  canClear = active > 0,
}: {
  open: boolean;
  onToggle: () => void;
  active: number;
  onClear?: () => void;
  canClear?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <>
      <Button variant={open ? "primary" : "outline"} onClick={onToggle} aria-expanded={open} icon={<Filter className="h-4 w-4" />}>
        {t("filters.button")}
        {active ? ` (${active})` : ""}
      </Button>
      {onClear && canClear && (
        <Button variant="ghost" onClick={onClear}>
          {t("filters.clear")}
        </Button>
      )}
    </>
  );
}

export function FilterPanel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <Card className={className}>
      <div className="space-y-4">{children}</div>
    </Card>
  );
}

/** A group of choices in the panel, with a small heading. */
export function FilterGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-xs text-muted">{label}</p>
      {children}
    </div>
  );
}

export interface FilterFlag {
  /** The key in the URL, with the value "true" (only these) or "false" (without these). */
  key: string;
  label: string;
}

/**
 * Properties to filter on. A click cycles through only these, without these and no filter, so
 * one row of chips covers both "only favorites" and "no favorites".
 */
export function TriStateChips({
  flags,
  state,
  onChange,
}: {
  flags: FilterFlag[];
  state: Record<string, string | undefined>;
  onChange: (key: string, value: string | null) => void;
}) {
  const { t } = useTranslation();
  return (
    <div>
      <p className="mb-1.5 text-xs text-muted">{t("filters.triStateHint")}</p>
      <div className="flex flex-wrap gap-1.5">
        {flags.map(({ key, label }) => {
          const value = state[key];
          const next = value === "true" ? "false" : value === "false" ? null : "true";
          const status = value === "true" ? t("filters.state.only") : value === "false" ? t("filters.state.without") : t("filters.state.off");
          return (
            <button
              key={key}
              type="button"
              data-flag={key}
              data-state={value === "true" ? "only" : value === "false" ? "without" : "off"}
              onClick={() => onChange(key, next)}
              aria-label={`${label}: ${status}`}
              title={t("filters.triStateHint")}
              className={clsx(
                "rounded-full border px-3 py-1 text-xs transition",
                value === "true" && "border-oak-500 bg-oak-500/15 text-oak-300",
                value === "false" && "border-red-500/60 bg-red-500/10 text-red-300 line-through",
                !value && "border-line text-muted hover:text-ink",
              )}
            >
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** One choice out of a few, or none: clicking the chosen one again clears it. */
export function ChoiceChips({
  name,
  options,
  value,
  onChange,
}: {
  name: string;
  options: { value: string; label: string }[];
  value: string | undefined;
  onChange: (value: string | null) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label={name}>
      {options.map((option) => {
        const chosen = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={chosen}
            onClick={() => onChange(chosen ? null : option.value)}
            className={clsx(
              "rounded-full border px-3 py-1 text-xs transition",
              chosen ? "border-oak-500 bg-oak-500/15 text-oak-300" : "border-line text-muted hover:text-ink",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
