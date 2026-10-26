import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { Card, EmptyState, Input, PageHeader, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { num } from "../../lib/format";
import { serverText, type ServerText } from "../../lib/serverText";

interface Item {
  item_id: number;
  source_name: string | null;
  name: string;
  group: string;
  group_label: ServerText;
  count: number;
}

function Items({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState("");
  const query = useQuery({
    queryKey: ["items", accountId],
    queryFn: () => api.get<{ items: Item[]; total: number; max_item_storage: number | null; note: ServerText }>("/api/v1/inventory/items", { account_id: accountId }),
  });
  if (query.isLoading || !query.data) return <Spinner />;
  const items = query.data.items.filter((i) => i.name.toLowerCase().includes(filter.toLowerCase()));
  const groups = new Map<string, Item[]>();
  for (const item of items) groups.set(item.group, [...(groups.get(item.group) ?? []), item]);
  return (
    <>
      <PageHeader
        title={t("account.items.title")}
        description={t("account.items.description", { total: num(query.data.total), max: num(query.data.max_item_storage), note: serverText("account", query.data.note) })}
        actions={<Input placeholder={t("account.items.search")} value={filter} onChange={(e) => setFilter(e.target.value)} className="w-56" />}
      />
      {groups.size === 0 ? (
        <EmptyState title={t("account.items.empty")} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[...groups.entries()].map(([group, list]) => (
            <Card key={group} title={serverText("account", list[0]?.group_label)} actions={<span className="text-xs text-muted">{num(list.reduce((s, i) => s + i.count, 0))}</span>}>
              <ul className="space-y-1 text-sm">
                {list.map((item) => (
                  <li key={item.item_id} className="flex justify-between gap-3">
                    <span title={item.source_name ?? undefined}>{item.name}</span>
                    <span className="font-semibold tabular-nums">{num(item.count)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}

export function ItemsPage() {
  return <RequireAccount>{(id) => <Items accountId={id} />}</RequireAccount>;
}
