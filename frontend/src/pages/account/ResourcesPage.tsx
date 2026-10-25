import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { Alert, Badge, Button, Card, Field, Input, PageHeader, Select, Spinner, Stat } from "../../components/ui";
import { useAccount } from "../../lib/account";
import { api, errorMessage } from "../../lib/api";
import { dateTime, num } from "../../lib/format";
import type { Facets } from "../../lib/types";

interface Resource {
  kind: string;
  key: string;
  quantity: number;
  updated_at: string;
  source: string;
}
const kindLabels: Record<string, string> = { candy: "Candy", xl_candy: "XL Candy", mega: "Mega Energy" };

function Resources({ accountId }: { accountId: number }) {
  const client = useQueryClient();
  const { account } = useAccount();
  const [form, setForm] = useState({ kind: "candy", key: "", quantity: 0 });
  const [error, setError] = useState<string | null>(null);
  const resources = useQuery({ queryKey: ["resources", accountId], queryFn: () => api.get<Resource[]>("/api/v1/resources", { account_id: accountId }) });
  const facets = useQuery({ queryKey: ["facets", accountId], queryFn: () => api.get<Facets>("/api/v1/pokemon/facets", { account_id: accountId }) });
  const save = useMutation({
    mutationFn: () => api.put("/api/v1/resources", { account_id: accountId, ...form }),
    onSuccess: () => {
      setError(null);
      void client.invalidateQueries({ queryKey: ["resources"] });
    },
    onError: (err) => setError(errorMessage(err)),
  });
  return (
    <>
      <PageHeader title="Stardust & Candy" description="Stardust en items komen uit PGSharp. Candy per soort exporteert PGSharp niet; die kun je hier zelf bijhouden." />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Stardust" value={num(account?.stardust ?? null)} hint="bron: PGSharp" />
        <Stat label="PokéCoins" value={num(account?.pokecoins ?? null)} hint="bron: PGSharp" />
      </div>
      <Card title="Handmatige hoeveelheden" className="mb-5">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Soort">
            <Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
              {Object.entries(kindLabels).map(([key, text]) => (
                <option key={key} value={key}>
                  {text}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Familie">
            <Select value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })} className="w-64">
              <option value="">Kies een familie</option>
              {facets.data?.families.map((f) => (
                <option key={f} value={f}>
                  {f.replace("FAMILY_", "").replaceAll("_", " ").toLowerCase()}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Aantal">
            <Input type="number" min={0} value={form.quantity} onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })} className="w-32" />
          </Field>
          <Button variant="primary" disabled={!form.key} loading={save.isPending} onClick={() => save.mutate()}>
            Opslaan
          </Button>
        </div>
        {error && (
          <div className="mt-3">
            <Alert tone="error">{error}</Alert>
          </div>
        )}
      </Card>
      {resources.isLoading ? (
        <Spinner />
      ) : (
        <Card title="Ingevoerde hoeveelheden">
          {!resources.data?.length ? (
            <p className="text-sm text-muted">Nog niets ingevoerd. Zonder invoer toont OAK candy als onbekend.</p>
          ) : (
            <table className="w-full text-sm">
              <tbody>
                {resources.data.map((r) => (
                  <tr key={`${r.kind}-${r.key}`} className="border-t border-line">
                    <td className="py-1.5">{r.key.replace("FAMILY_", "").replaceAll("_", " ").toLowerCase()}</td>
                    <td>{kindLabels[r.kind]}</td>
                    <td className="tabular-nums">{num(r.quantity)}</td>
                    <td>
                      <Badge>handmatig</Badge>
                    </td>
                    <td className="text-xs text-muted">{dateTime(r.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}
    </>
  );
}

export function ResourcesPage() {
  return <RequireAccount>{(id) => <Resources accountId={id} />}</RequireAccount>;
}
