import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { ReadinessBadge, TypeBadge } from "../../components/pokemon";
import { Alert, Button, Card, Field, Input, PageHeader, Select, Spinner } from "../../components/ui";
import { api, errorMessage } from "../../lib/api";
import { num } from "../../lib/format";
import { leagueNames, typeNames } from "../../lib/i18n";

interface Member {
  role: string;
  pokemon_id: number;
  name: string | null;
  target: string;
  is_evolution: boolean;
  cp: number | null;
  best_cp: number;
  iv_rank: number;
  species_rank: number | null;
  readiness: string;
  stardust: number | null;
  candy: number | null;
  xl_candy: number | null;
  moveset_quality: string;
  recommended_moveset: string[];
  types: string[];
}
interface Variant {
  mode: string;
  label: string;
  team: Member[] | null;
  message?: string;
  score?: number;
  investment?: { stardust: number };
  shared_weaknesses?: string[];
  move_type_coverage?: string[];
}
interface SavedTeam {
  id: number;
  name: string;
  league: string | null;
  members: { position: number; role: string | null; pokemon_id: number; name: string | null; cp: number | null; in_inventory: boolean }[];
}

const roleLabels: Record<string, string> = { lead: "Lead", switch: "Safe switch", closer: "Closer" };

function TeamBuilder({ accountId }: { accountId: number }) {
  const client = useQueryClient();
  const [league, setLeague] = useState("great");
  const [budget, setBudget] = useState(100_000);
  const [message, setMessage] = useState<string | null>(null);
  const build = useMutation({
    mutationFn: () => api.post<{ method: string; variants: Variant[] }>("/api/v1/battles/team-builder", { account_id: accountId, league, stardust_budget: budget }),
  });
  const teams = useQuery({ queryKey: ["teams", accountId], queryFn: () => api.get<SavedTeam[]>("/api/v1/battles/teams", { account_id: accountId }) });
  const save = useMutation({
    mutationFn: (variant: Variant) =>
      api.post("/api/v1/battles/teams", {
        account_id: accountId,
        name: `${leagueNames[league]} – ${variant.label}`,
        kind: "pvp",
        league,
        members: variant.team?.map((m) => ({ pokemon_id: m.pokemon_id, role: m.role })) ?? [],
      }),
    onSuccess: () => {
      setMessage("Team opgeslagen.");
      void client.invalidateQueries({ queryKey: ["teams"] });
    },
    onError: (error) => setMessage(errorMessage(error)),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/api/v1/battles/teams/${id}`, undefined, { account_id: accountId }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["teams"] }),
  });
  return (
    <>
      <PageHeader title="Team Builder" description="Drie teamvarianten uit je eigen collectie: direct inzetbaar, met beperkte upgrades en het beste toekomstige team." />
      <Card className="mb-5">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="League">
            <Select value={league} onChange={(e) => setLeague(e.target.value)}>
              {Object.entries(leagueNames).map(([key, name]) => (
                <option key={key} value={key}>
                  {name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Stardust-budget per Pokémon (beperkte upgrades)">
            <Input type="number" min={0} step={10000} value={budget} onChange={(e) => setBudget(Number(e.target.value))} className="w-48" />
          </Field>
          <Button variant="primary" loading={build.isPending} onClick={() => build.mutate()}>
            Teams voorstellen
          </Button>
        </div>
      </Card>
      {build.error && <Alert tone="error">{errorMessage(build.error)}</Alert>}
      {message && <Alert tone="success">{message}</Alert>}
      {build.data && (
        <>
          <Alert tone="info">{build.data.method}</Alert>
          <div className="mt-4 grid gap-4 xl:grid-cols-3">
            {build.data.variants.map((variant) => (
              <Card key={variant.mode} title={variant.label} actions={variant.team && <Button size="sm" onClick={() => save.mutate(variant)}>Opslaan</Button>}>
                {!variant.team ? (
                  <p className="text-sm text-muted">{variant.message}</p>
                ) : (
                  <>
                    <ol className="space-y-3">
                      {variant.team.map((m) => (
                        <li key={m.pokemon_id} className="rounded-lg border border-line p-3">
                          <p className="text-xs uppercase tracking-wide text-muted">{roleLabels[m.role] ?? m.role}</p>
                          <Link to={`/pokemon/${m.pokemon_id}`} className="font-medium hover:text-oak-300">
                            {m.name} {m.is_evolution && `→ ${m.target}`}
                          </Link>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {m.types.map((t) => (
                              <TypeBadge key={t} type={t} />
                            ))}
                            <ReadinessBadge readiness={m.readiness} />
                          </div>
                          <p className="mt-1 text-xs text-muted">
                            CP {num(m.cp, "?")} → {num(m.best_cp)} · IV-rang {m.iv_rank} · soortrang {m.species_rank ?? "–"}
                          </p>
                          <p className="text-xs text-muted">Aanvallen: {m.recommended_moveset.join(" · ") || "onbekend"}</p>
                        </li>
                      ))}
                    </ol>
                    <p className="mt-3 text-xs text-muted">
                      Investering: {num(variant.investment?.stardust ?? 0)} stardust · Gedeelde zwaktes:{" "}
                      {variant.shared_weaknesses?.length ? variant.shared_weaknesses.map((t) => typeNames[t] ?? t).join(", ") : "geen"}
                    </p>
                  </>
                )}
              </Card>
            ))}
          </div>
        </>
      )}
      <Card className="mt-5" title="Opgeslagen teams">
        {teams.isLoading ? (
          <Spinner />
        ) : !teams.data?.length ? (
          <p className="text-sm text-muted">Nog geen teams opgeslagen.</p>
        ) : (
          <ul className="divide-y divide-line">
            {teams.data.map((team) => (
              <li key={team.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                <span>
                  <span className="font-medium">{team.name}</span>
                  <span className="ml-2 text-muted">
                    {team.members.map((m) => `${m.name}${m.in_inventory ? "" : " (weg)"}`).join(" · ")}
                  </span>
                </span>
                <Button size="sm" variant="ghost" onClick={() => remove.mutate(team.id)}>
                  Verwijderen
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

export function TeamBuilderPage() {
  return <RequireAccount>{(id) => <TeamBuilder accountId={id} />}</RequireAccount>;
}
