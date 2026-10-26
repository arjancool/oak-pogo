import { useState } from "react";
import { useTranslation } from "react-i18next";

import { confirmationKindLabels, label } from "../../lib/i18n";
import type { ConfirmationItem } from "../../lib/schemas";
import { Alert, Button, Checkbox, Dialog } from "../ui";

function kindsText(item: ConfirmationItem): string {
  return item.kinds.map((k) => label(confirmationKindLabels, k)).join("; ");
}

/**
 * Per-Pokémon confirmation before favorites, Pokémon with an unknown catch date, rule-protected
 * Pokémon or vintage Pokémon whose protection was lifted go on a transfer list (ADR-0019).
 * Nothing is ticked in advance: every Pokémon needs its own explicit choice.
 */
export function ConfirmTransferDialog({
  items,
  busy,
  onCancel,
  onConfirm,
}: {
  items: ConfirmationItem[];
  busy?: boolean;
  onCancel: () => void;
  onConfirm: (ids: number[]) => void;
}) {
  const { t } = useTranslation();
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const toggle = (id: number, value: boolean) =>
    setChecked((current) => {
      const next = new Set(current);
      if (value) next.add(id);
      else next.delete(id);
      return next;
    });
  return (
    <Dialog
      open={items.length > 0}
      onClose={onCancel}
      title={t("confirmTransfer.title")}
      wide
      footer={
        <>
          <Button onClick={onCancel}>{t("common.cancel")}</Button>
          <Button variant="danger" disabled={checked.size === 0} loading={busy} onClick={() => onConfirm([...checked])}>
            {t("confirmTransfer.confirm", { count: checked.size })}
          </Button>
        </>
      }
    >
      <Alert tone="warning">
        {t("confirmTransfer.warning")}
      </Alert>
      <ul className="mt-3 divide-y divide-line text-sm">
        {items.map((item) => (
          <li key={item.pokemon_id} className="flex items-start gap-3 py-2">
            <Checkbox
              checked={checked.has(item.pokemon_id)}
              onChange={(value) => toggle(item.pokemon_id, value)}
              label={<span className="sr-only">{t("confirmTransfer.confirmOne", { name: item.name })}</span>}
            />
            <div>
              <p className="font-medium">
                {item.name} <span className="text-muted">CP {item.cp ?? "?"}</span>
              </p>
              <p className="text-xs text-amber-300">{kindsText(item)}</p>
              {item.message !== kindsText(item) && <p className="text-xs text-muted">{item.message}</p>}
              {item.new_reasons.length > 0 && (
                <p className="text-xs font-medium text-amber-200">{t("confirmTransfer.newReasons", { reasons: item.new_reasons.join(", ") })}</p>
              )}
            </div>
          </li>
        ))}
      </ul>
    </Dialog>
  );
}
