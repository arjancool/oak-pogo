/** The action list in the chosen language, for the page, the CSV and the printable checklist
 * (issue #31). The reasons are server texts, so they follow the language like everywhere else. */
import i18n from "i18next";

import { newReasons } from "../../components/cleanup/ConfirmTransferDialog";
import { toCsv } from "../../lib/csv";
import type { ActionList } from "../../lib/schemas";
import { serverText } from "../../lib/serverText";

type Item = ActionList["items"][number];

export function reasonText(item: Item): string {
  return item.reason_texts.length ? item.reason_texts.map((r) => serverText("reasons", r)).join("; ") : (item.reason ?? "");
}

export function protectionText(item: Item): string {
  return item.protection_texts.length ? item.protection_texts.map((r) => serverText("protections", r)).join(", ") : item.protection.join(", ");
}

export function confirmationText(item: Item): string {
  const confirmation = item.needs_confirmation;
  if (!confirmation) return "";
  if (confirmation.new_reasons.length) return i18n.t("cleanup.list.newReasons", { reasons: newReasons(confirmation) });
  return confirmation.message_texts.length ? confirmation.message_texts.map((m) => serverText("guard", m)).join("; ") : confirmation.message;
}

/** Why an item is not on the checklist, or "" when it is. */
export function heldBackText(item: Item): string {
  if (item.blocked) return serverText("guard", item.blocked_text ?? item.blocked);
  if (item.needs_confirmation) return i18n.t("cleanup.list.reconfirm", { reason: confirmationText(item) });
  if (!item.still_in_inventory) return i18n.t("cleanup.list.gone");
  return "";
}

const COLUMNS = [
  "pokemon",
  "form",
  "cp",
  "atk",
  "def",
  "sta",
  "ivPercent",
  "reason",
  "protection",
  "sourceId",
  "status",
  "executable",
  "heldBack",
] as const;

export function actionListCsv(data: ActionList): string {
  const header = COLUMNS.map((column) => i18n.t(`cleanup.list.csv.${column}`));
  const yes = i18n.t("cleanup.list.csv.yes");
  const no = i18n.t("cleanup.list.csv.no");
  const rows = data.items.map((item) => {
    const p = item.pokemon;
    return [
      p.species_name,
      p.form_label,
      p.cp,
      p.iv_attack,
      p.iv_defense,
      p.iv_stamina,
      p.iv_percent,
      reasonText(item),
      protectionText(item),
      p.source_pokemon_id,
      item.status,
      item.executable ? yes : no,
      heldBackText(item),
    ];
  });
  return toCsv([header, ...rows]);
}
