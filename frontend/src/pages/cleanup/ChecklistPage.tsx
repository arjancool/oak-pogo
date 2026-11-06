import { useQuery } from "@tanstack/react-query";
import { Printer } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";

import { Button, Spinner } from "../../components/ui";
import { useAccount } from "../../lib/account";
import { api } from "../../lib/api";
import { ivs, num } from "../../lib/format";
import { actionList } from "../../lib/schemas";
import { protectionText, reasonText } from "./actionListText";

/** The printable checklist of the action list, in the chosen language (issue #31). Only what can
 * be done is on it; held back Pokémon are counted, not listed. OAK transfers nothing itself. */
export function ChecklistPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const { accountId: activeAccount } = useAccount();
  const fromUrl = Number(params.get("account"));
  const accountId = Number.isInteger(fromUrl) && fromUrl > 0 ? fromUrl : activeAccount;
  const sort = params.get("sort") === "-cp" ? "-cp" : "cp";
  const query = useQuery({
    queryKey: ["action-list", accountId, sort],
    queryFn: async () => actionList.parse(await api.get("/api/v1/cleanup/action-list", { account_id: accountId, sort })),
    enabled: accountId !== null,
  });
  useEffect(() => {
    document.title = t("cleanup.checklist.title");
  }, [t]);
  if (accountId === null || query.isLoading) return <Spinner />;
  if (!query.data) return <p className="p-6">{t("common.unknown")}</p>;
  const items = query.data.items.filter((item) => item.executable);
  const heldBack = query.data.items.filter((item) => item.status === "open" && !item.executable).length;
  return (
    <main className="min-h-screen bg-white p-6 text-black">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">{t("cleanup.checklist.title")}</h1>
        <Button className="no-print" variant="outline" icon={<Printer className="h-4 w-4" />} onClick={() => window.print()}>
          {t("cleanup.checklist.print")}
        </Button>
      </div>
      <p className="mb-2 text-sm">{t(sort === "cp" ? "cleanup.checklist.introAsc" : "cleanup.checklist.introDesc")}</p>
      {heldBack > 0 && <p className="mb-2 text-sm font-semibold">{t("cleanup.checklist.heldBack", { count: heldBack })}</p>}
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            {["", t("cleanup.checklist.columns.pokemon"), t("cleanup.checklist.columns.form"), "CP", "IV", t("cleanup.list.columns.reason"), t("cleanup.list.columns.protection"), t("cleanup.list.columns.sourceId")].map((title, index) => (
              <th key={index} className="border border-neutral-400 px-1.5 py-1 text-left">
                {title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.pokemon.id}>
              <td className="border border-neutral-400 px-1.5 py-1">☐</td>
              <td className="border border-neutral-400 px-1.5 py-1">{item.pokemon.species_name ?? `#${item.pokemon.species_id}`}</td>
              <td className="border border-neutral-400 px-1.5 py-1">{item.pokemon.form_label ?? ""}</td>
              <td className="border border-neutral-400 px-1.5 py-1 tabular-nums">{num(item.pokemon.cp, "?")}</td>
              <td className="border border-neutral-400 px-1.5 py-1 font-mono">{ivs(item.pokemon.iv_attack, item.pokemon.iv_defense, item.pokemon.iv_stamina)}</td>
              <td className="border border-neutral-400 px-1.5 py-1">{reasonText(item)}</td>
              <td className="border border-neutral-400 px-1.5 py-1">{protectionText(item) || "—"}</td>
              <td className="border border-neutral-400 px-1.5 py-1 font-mono text-[10px]">{item.pokemon.source_pokemon_id}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
