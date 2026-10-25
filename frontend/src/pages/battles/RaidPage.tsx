import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { TypeBadge } from "../../components/pokemon";
import { Alert, Badge, Button, Card, PageHeader, SortHeader, Spinner } from "../../components/ui";
import { api, errorMessage } from "../../lib/api";
import { level, num } from "../../lib/format";
import { sortRows } from "../../lib/sort";
import { useUrlState } from "../../lib/useUrlState";
import { SpeciesPicker, type SpeciesOption } from "./shared";

interface Counter {
  pokemon_id: number;
  name: string | null;
  form_label: string | null;
  shadow: boolean;
  cp: number | null;
  level: number | null;
  types: string[];
  current: { dps: number; fast: string | null; charged: string | null; effectiveness: number };
  best_moveset: { dps: number; fast: string | null; charged: string | null; needs_tm: boolean; needs_elite_tm: boolean };
  weak_to_boss: boolean;
}

const DEFAULT_SORT = "-dps";
const COLUMNS = {
  name: (c: RankedCounter) => c.name?.toLocaleLowerCase("nl"),
  cp: (c: RankedCounter) => c.cp,
  dps: (c: RankedCounter) => c.current.dps,
  best_dps: (c: RankedCounter) => c.best_moveset.dps,
};

type RankedCounter = Counter & { rank: number };

function Raids({ accountId }: { accountId: number }) {
  const [boss, setBoss] = useState<SpeciesOption | null>(null);
  const [state, update] = useUrlState();
  const sort = state.sort ?? DEFAULT_SORT;
  const header = (label: string, sortKey: string, ascendingFirst = false) => (
    <SortHeader label={label} sortKey={sortKey} sort={sort} onSort={(value) => update({ sort: value === DEFAULT_SORT ? null : value })} ascendingFirst={ascendingFirst} />
  );
  const run = useMutation({
    mutationFn: (bossKey: string | null) =>
      api.post<{ method: string; counters: Counter[]; boss: { name: string; types: string[] } | null; mode: string }>("/api/v1/battles/raid-counters", {
        account_id: accountId,
        boss_key: bossKey,
      }),
  });
  const { mutate } = run;
  useEffect(() => mutate(boss?.key ?? null), [boss, mutate]);
  const data = run.data;
  const counters = data ? sortRows<RankedCounter>(data.counters.map((c, index) => ({ ...c, rank: index + 1 })), sort, COLUMNS) : [];
  return (
    <>
      <PageHeader
        title="Raids"
        description="Zonder baas zie je je beste algemene aanvallers. Kies een raid-baas voor counters tegen die specifieke tegenstander."
      />
      <Card className="mb-5">
        <div className="flex flex-wrap items-center gap-3">
          <div className="w-full max-w-md">
            <SpeciesPicker onPick={setBoss} placeholder="Raid-baas zoeken, bijv. kyogre" />
          </div>
          {boss && (
            <>
              <span className="font-medium">{boss.name}</span>
              {boss.types.map((t) => (
                <TypeBadge key={t} type={t} />
              ))}
              <Button size="sm" variant="ghost" onClick={() => setBoss(null)}>
                Algemene aanvallers
              </Button>
            </>
          )}
        </div>
      </Card>
      {run.isPending && <Spinner />}
      {run.error && <Alert tone="error">{errorMessage(run.error)}</Alert>}
      {data && (
        <Card title={data.boss ? `Counters tegen ${data.boss.name}` : "Beste algemene raid-aanvallers"}>
          <Alert tone="info">{data.method}</Alert>
          <p className="mt-2 text-xs text-muted">
            De {num(data.counters.length)} aanvallers met de hoogste DPS met hun huidige aanvallen. Klik op een kolomkop om binnen deze lijst te
            sorteren. Het nummer blijft hun plek op DPS.
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm [&_td]:pr-3 [&_th]:pr-3">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="py-2">#</th>
                  <th>
                    {header("Pokémon", "name", true)} · {header("CP", "cp")}
                  </th>
                  <th>{header("DPS nu", "dps")}</th>
                  <th>Huidige aanvallen</th>
                  <th>{header("Beste moveset", "best_dps")}</th>
                  <th>Opmerkingen</th>
                </tr>
              </thead>
              <tbody>
                {counters.map((c) => (
                  <tr key={c.pokemon_id} className="border-t border-line align-top">
                    <td className="py-2 pr-2 text-muted">{c.rank}</td>
                    <td className="pr-3">
                      <Link to={`/pokemon/${c.pokemon_id}`} className="font-medium hover:text-oak-300">
                        {c.name}
                        {c.form_label ? ` (${c.form_label})` : ""}
                      </Link>
                      {c.shadow && <Badge className="ml-1" color="#a855f7">Shadow</Badge>}
                      <span className="block text-xs text-muted">
                        CP {num(c.cp, "?")} · L{level(c.level)}
                      </span>
                    </td>
                    <td className="pr-3 font-semibold tabular-nums">{c.current.dps.toLocaleString("nl-NL")}</td>
                    <td className="pr-3 text-xs">
                      {c.current.fast} · {c.current.charged ?? "alleen snelle aanval"}
                    </td>
                    <td className="pr-3 text-xs">
                      {c.best_moveset.needs_tm ? (
                        <>
                          {c.best_moveset.fast} · {c.best_moveset.charged} ({c.best_moveset.dps.toLocaleString("nl-NL")} DPS)
                          {c.best_moveset.needs_elite_tm && <span className="block text-amber-300">Elite TM nodig</span>}
                        </>
                      ) : (
                        <span className="text-muted">Huidige moveset is al de beste</span>
                      )}
                    </td>
                    <td className="text-xs">
                      {c.weak_to_boss && <Badge color="#f87171">Zwak tegen baas-type</Badge>}
                      {c.current.effectiveness > 1 && <Badge color="#34d399">Supereffectief</Badge>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}

export function RaidPage() {
  return <RequireAccount>{(id) => <Raids accountId={id} />}</RequireAccount>;
}
