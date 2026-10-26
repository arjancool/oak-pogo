import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ParseKeys } from "i18next";
import { useState } from "react";
import { useTranslation } from "react-i18next";

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
const kindLabels: Record<string, ParseKeys> = {
  candy: "account.resources.kinds.candy",
  xl_candy: "account.resources.kinds.xl_candy",
  mega: "account.resources.kinds.mega",
};

function Resources({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
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
      <PageHeader title={t("account.resources.title")} description={t("account.resources.description")} />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label={t("account.resources.stardust")} value={num(account?.stardust ?? null)} hint={t("account.resources.sourcePgsharp")} />
        <Stat label={t("account.resources.pokecoins")} value={num(account?.pokecoins ?? null)} hint={t("account.resources.sourcePgsharp")} />
      </div>
      <Card title={t("account.resources.manual")} className="mb-5">
        <div className="flex flex-wrap items-end gap-3">
          <Field label={t("account.resources.kind")}>
            <Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
              {Object.entries(kindLabels).map(([key, text]) => (
                <option key={key} value={key}>
                  {t(text)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("account.resources.family")}>
            <Select value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })} className="w-64">
              <option value="">{t("account.resources.chooseFamily")}</option>
              {facets.data?.families.map((f) => (
                <option key={f} value={f}>
                  {f.replace("FAMILY_", "").replaceAll("_", " ").toLowerCase()}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("account.resources.quantity")}>
            <Input type="number" min={0} value={form.quantity} onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })} className="w-32" />
          </Field>
          <Button variant="primary" disabled={!form.key} loading={save.isPending} onClick={() => save.mutate()}>
            {t("account.resources.save")}
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
        <Card title={t("account.resources.entered")}>
          {!resources.data?.length ? (
            <p className="text-sm text-muted">{t("account.resources.nothingEntered")}</p>
          ) : (
            <table className="w-full text-sm">
              <tbody>
                {resources.data.map((r) => {
                  const kind = kindLabels[r.kind];
                  return (
                    <tr key={`${r.kind}-${r.key}`} className="border-t border-line">
                      <td className="py-1.5">{r.key.replace("FAMILY_", "").replaceAll("_", " ").toLowerCase()}</td>
                      <td>{kind && t(kind)}</td>
                      <td className="tabular-nums">{num(r.quantity)}</td>
                      <td>
                        <Badge>{t("account.resources.manualBadge")}</Badge>
                      </td>
                      <td className="text-xs text-muted">{dateTime(r.updated_at)}</td>
                    </tr>
                  );
                })}
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
