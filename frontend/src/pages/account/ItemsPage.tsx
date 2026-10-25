import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { Card, EmptyState, Input, PageHeader, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { num } from "../../lib/format";

interface Item {
  item_id: number;
  source_name: string | null;
  name: string;
  group: string;
  group_label: string;
  count: number;
}

function Items({ accountId }: { accountId: number }) {
  const [filter, setFilter] = useState("");
  const query = useQuery({
    queryKey: ["items", accountId],
    queryFn: () => api.get<{ items: Item[]; total: number; max_item_storage: number | null; note: string }>("/api/v1/inventory/items", { account_id: accountId }),
  });
  if (query.isLoading || !query.data) return <Spinner />;
  const items = query.data.items.filter((i) => i.name.toLowerCase().includes(filter.toLowerCase()));
  const groups = new Map<string, Item[]>();
  for (const item of items) groups.set(item.group_label, [...(groups.get(item.group_label) ?? []), item]);
  return (
    <>
      <PageHeader
        title="Item Bag"
        description={`${num(query.data.total)} van ${num(query.data.max_item_storage)} plaatsen. ${query.data.note}`}
        actions={<Input placeholder="Item zoeken…" value={filter} onChange={(e) => setFilter(e.target.value)} className="w-56" />}
      />
      {groups.size === 0 ? (
        <EmptyState title="Geen items" />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[...groups.entries()].map(([group, list]) => (
            <Card key={group} title={group} actions={<span className="text-xs text-muted">{num(list.reduce((s, i) => s + i.count, 0))}</span>}>
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
