import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { PokemonSprite, ScoreMeter, TypeBadge } from "../../components/pokemon";
import { Alert, Badge, Card, EmptyState, PageHeader, Spinner } from "../../components/ui";
import { api, errorMessage } from "../../lib/api";
import { level, num } from "../../lib/format";

interface Defender {
  pokemon_id: number;
  name: string | null;
  form_label: string | null;
  species_id: number;
  shadow: boolean;
  cp: number | null;
  level: number | null;
  types: string[];
  hp: number;
  defense: number;
  bulk: number;
  value: number | null;
  fast_move: string | null;
  charged_moves: string[];
  reasons: string[];
  confidence: "high" | "medium" | "low";
  same_species: number;
  in_gym: boolean | null;
}

interface GymOverview {
  defenders: Defender[];
  excluded: Partial<Record<"not_deployable" | "unknown_form" | "unknown_stats", number>>;
  reference: { name: string | null; level: number } | null;
  unknown_reason: string | null;
  method: string;
  notes: string[];
  source: string;
  game_data_version: number;
}

const confidenceLabels: Record<Defender["confidence"], string> = { high: "Hoog", medium: "Gemiddeld", low: "Laag" };

function excludedText(excluded: GymOverview["excluded"]): string | null {
  const parts = [
    excluded.not_deployable ? `${num(excluded.not_deployable)} mogen volgens de Game Data niet in een gym` : null,
    excluded.unknown_form ? `${num(excluded.unknown_form)} hebben een vorm die de Game Data niet kent` : null,
    excluded.unknown_stats ? `${num(excluded.unknown_stats)} missen level of IV's` : null,
  ].filter(Boolean);
  return parts.length ? `Niet meegeteld: ${parts.join(", ")}.` : null;
}

function Gyms({ accountId }: { accountId: number }) {
  const query = useQuery({
    queryKey: ["gym-defenders", accountId],
    queryFn: () => api.get<GymOverview>("/api/v1/battles/gym-defenders", { account_id: accountId }),
  });
  const data = query.data;
  const excluded = data ? excludedText(data.excluded) : null;
  return (
    <>
      <PageHeader
        title="Gymverdedigers"
        description="De Pokémon die een gym het langst vasthouden: veel HP en Defense, zodat een aanvaller veel aanvallen nodig heeft. Per soort je sterkste exemplaar."
      />
      {query.isLoading && <Spinner />}
      {query.error && <Alert tone="error">{errorMessage(query.error)}</Alert>}
      {data?.unknown_reason && <Alert tone="warning">{data.unknown_reason}</Alert>}
      {data && !data.unknown_reason && (
        <>
          <Card className="mb-5">
            <details>
              <summary className="cursor-pointer text-sm font-medium">Hoe OAK dit berekent</summary>
              <p className="mt-2 text-sm text-muted">{data.method}</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted">
                {data.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </details>
            <p className="mt-3 text-xs text-muted">
              Bron: {data.source}, Game Data-versie {data.game_data_version}.{excluded ? ` ${excluded}` : ""}
            </p>
          </Card>
          {data.defenders.length === 0 ? (
            <EmptyState title="Geen verdedigers gevonden">Er staat geen Pokémon in je collectie die volgens de Game Data in een gym mag.</EmptyState>
          ) : (
            <Card title={`Je ${data.defenders.length} sterkste verdedigers`}>
              <ol className="divide-y divide-line">
                {data.defenders.map((d, index) => (
                  <li key={d.pokemon_id} className="flex flex-wrap items-start gap-3 py-3">
                    <span className="w-6 pt-2 text-right text-sm text-muted">{index + 1}</span>
                    <PokemonSprite dex={d.species_id} types={d.types} size={40} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link to={`/pokemon/${d.pokemon_id}`} className="font-medium hover:text-oak-300">
                          {d.name}
                          {d.form_label ? ` (${d.form_label})` : ""}
                        </Link>
                        {d.types.map((t) => (
                          <TypeBadge key={t} type={t} />
                        ))}
                        {d.shadow && <Badge color="#a855f7">Shadow</Badge>}
                        {d.in_gym && <Badge color="#38bdf8">Staat in een gym</Badge>}
                        <ScoreMeter label="Verdedigingswaarde" value={d.value} />
                      </div>
                      <p className="mt-1 text-xs text-muted">
                        CP {num(d.cp, "?")} · L{level(d.level)}
                        {d.fast_move ? ` · ${[d.fast_move, ...d.charged_moves].join(", ")}` : ""}
                        {d.same_species > 0 ? ` · nog ${d.same_species} andere van deze soort` : ""}
                      </p>
                      <ul className="mt-1 space-y-0.5 text-xs text-muted">
                        {d.reasons.map((reason) => (
                          <li key={reason}>{reason}</li>
                        ))}
                        <li>Betrouwbaarheid: {confidenceLabels[d.confidence]}</li>
                      </ul>
                    </div>
                  </li>
                ))}
              </ol>
            </Card>
          )}
        </>
      )}
    </>
  );
}

export function GymPage() {
  return <RequireAccount>{(id) => <Gyms accountId={id} />}</RequireAccount>;
}
