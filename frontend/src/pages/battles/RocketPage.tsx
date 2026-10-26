import { useMutation } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { TypeBadge } from "../../components/pokemon";
import { Alert, Badge, Button, Card, PageHeader, Spinner } from "../../components/ui";
import { api, errorMessage } from "../../lib/api";
import { num } from "../../lib/format";
import { SpeciesPicker, type SpeciesOption } from "./shared";

interface Result {
  opponent: string;
  types: string[];
  counters: { pokemon_id: number; name: string | null; form_label: string | null; cp: number | null; types: string[]; score: number; resists: boolean; weak: boolean; moves: string[] }[];
}

function Rocket({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
  const [opponents, setOpponents] = useState<SpeciesOption[]>([]);
  const run = useMutation({
    mutationFn: () =>
      api.post<{ lineup_note: string; method: string; results: Result[] }>("/api/v1/battles/rocket-counters", {
        account_id: accountId,
        opponent_keys: opponents.map((o) => o.key),
      }),
  });
  return (
    <>
      <PageHeader title={t("battles.rocket.title")} description={t("battles.rocket.description")} />
      <Alert tone="warning" title={t("battles.rocket.noLineupsTitle")}>
        {t("battles.rocket.noLineups")}
      </Alert>
      <Card className="mt-4">
        <div className="space-y-3">
          <div className="max-w-md">
            <SpeciesPicker
              placeholder={t("battles.rocket.add")}
              onPick={(option) => setOpponents((current) => (current.length >= 3 || current.some((c) => c.key === option.key) ? current : [...current, option]))}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            {opponents.map((o) => (
              <Badge key={o.key}>
                {o.name}
                <button aria-label={t("battles.rocket.remove", { name: o.name })} onClick={() => setOpponents((current) => current.filter((c) => c.key !== o.key))}>
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
          </div>
          <Button variant="primary" disabled={!opponents.length} loading={run.isPending} onClick={() => run.mutate()}>
            {t("battles.rocket.find")}
          </Button>
        </div>
      </Card>
      {run.isPending && <Spinner />}
      {run.error && <Alert tone="error">{errorMessage(run.error)}</Alert>}
      {run.data && (
        <>
          <p className="mt-4 text-xs text-muted">{run.data.method}</p>
          <div className="mt-2 grid gap-4 lg:grid-cols-3">
            {run.data.results.map((result) => (
              <Card key={result.opponent} title={result.opponent} actions={result.types.map((type) => <TypeBadge key={type} type={type} />)}>
                <ol className="space-y-2 text-sm">
                  {result.counters.map((c) => (
                    <li key={c.pokemon_id} className="flex items-start justify-between gap-2">
                      <span>
                        <Link to={`/pokemon/${c.pokemon_id}`} className="font-medium hover:text-oak-300">
                          {c.name}
                          {c.form_label ? ` (${c.form_label})` : ""}
                        </Link>
                        <span className="block text-xs text-muted">
                          CP {num(c.cp, "?")} · {c.moves.join(" · ")}
                        </span>
                      </span>
                      <span className="flex flex-col items-end gap-1">
                        {c.resists && <Badge color="#34d399">{t("battles.rocket.resists")}</Badge>}
                        {c.weak && <Badge color="#f87171">{t("battles.rocket.weak")}</Badge>}
                      </span>
                    </li>
                  ))}
                </ol>
              </Card>
            ))}
          </div>
        </>
      )}
    </>
  );
}

export function RocketPage() {
  return <RequireAccount>{(id) => <Rocket accountId={id} />}</RequireAccount>;
}
