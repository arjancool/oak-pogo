import { Link } from "react-router";

import { Alert, Badge, Card, EmptyState, PageHeader, Spinner } from "../../components/ui";
import { errorMessage } from "../../lib/api";
import { num } from "../../lib/format";
import { CupRules, useLeagues } from "./shared";

export function CupsPage() {
  const leagues = useLeagues();
  const cups = (leagues.data ?? []).filter((l) => l.kind === "cup");
  return (
    <>
      <PageHeader
        title="Cups"
        description="Speciale formats met eigen regels, zoals de Fantasy Cup. OAK toont de cups die PvPoke nu op zijn site heeft. Daar zitten cups uit de GO Battle League tussen, maar ook toernooien uit de community. Welke cup in het spel loopt, zie je in Pokémon GO zelf."
      />
      {leagues.isLoading && <Spinner />}
      {leagues.error && <Alert tone="error">{errorMessage(leagues.error)}</Alert>}
      {leagues.data && cups.length === 0 && (
        <EmptyState title="Geen cups bekend">De actieve Game Data bevat geen cups. Werk de Game Data bij onder Beheer, dan haalt OAK ze op bij PvPoke.</EmptyState>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        {cups.map((cup) => (
          <Card
            key={cup.id}
            title={cup.name}
            actions={
              cup.ranked_species ? (
                <Badge color="#34d399">Ranglijst van PvPoke</Badge>
              ) : (
                <Badge color="#94a3b8" title="Je Pokémon worden alleen op IV-rang gesorteerd.">
                  Geen ranglijst
                </Badge>
              )
            }
          >
            <CupRules info={cup} />
            <p className="mt-3 text-xs text-muted">
              {num(cup.eligible_species)} soorten en vormen mogen mee volgens de regels van PvPoke.
              {cup.ranked_species ? ` PvPoke rangschikt er ${num(cup.ranked_species)}.` : ""}
            </p>
            <div className="mt-3 flex flex-wrap gap-3 text-sm">
              <Link to={`/battles/${cup.id}`} className="text-oak-400 underline">
                Je Pokémon voor deze cup
              </Link>
              <Link to={`/battles/team-builder?league=${cup.id}`} className="text-oak-400 underline">
                Team voorstellen
              </Link>
              {cup.link && (
                <a href={cup.link} target="_blank" rel="noreferrer noopener" className="text-muted underline">
                  Over dit toernooi
                </a>
              )}
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
