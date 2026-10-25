import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert, Badge, Button, Card, KeyValue, PageHeader, Spinner } from "../../components/ui";
import { useAuth } from "../../lib/auth";
import { api, errorMessage } from "../../lib/api";
import { bytes, dateTime, num } from "../../lib/format";
import type { GameDataStatus, GameDataVersion } from "../../lib/types";

const POLL_MS = 3000;
const UPLOAD_FIELDS = [
  { name: "pokeminers", label: "PokeMiners GAME_MASTER.json", required: true },
  { name: "pvpoke", label: "PvPoke gamemaster.json", required: false },
  { name: "rankings_great", label: "PvPoke rankings Great League", required: false },
  { name: "rankings_ultra", label: "PvPoke rankings Ultra League", required: false },
  { name: "rankings_master", label: "PvPoke rankings Master League", required: false },
] as const;

const statusText: Record<string, string> = { active: "actief", archived: "bewaard", ready: "klaar", pruned: "opgeruimd", failed: "mislukt" };
const ACTIVATABLE = ["archived", "ready"];

function Summary({ version }: { version: GameDataVersion }) {
  const s = version.summary ?? {};
  const rankings = (s.rankings ?? {}) as Record<string, number | null>;
  return (
    <KeyValue
      items={[
        ["Versie", `#${version.id} (${version.origin === "upload" ? "handmatige upload" : "download"})`],
        ["Geactiveerd", dateTime(version.activated_at)],
        ["Soorten", num(s.species as number)],
        ["Vormen", num(s.forms as number)],
        ["Aanvallen", num(s.moves as number)],
        ["Vormen gekoppeld aan PvPoke", num(s.pvpoke_mapped_forms as number)],
        ["League-rankings", Object.entries(rankings).map(([league, count]) => `${league}: ${num(count)}`).join(" · ") || "geen"],
        ["Maximaal level zonder Best Buddy", String(s.max_normal_level ?? "onbekend")],
      ]}
    />
  );
}

export function GameDataPage() {
  const client = useQueryClient();
  const { user } = useAuth();
  const owner = user?.role === "owner";
  const [message, setMessage] = useState<{ tone: "success" | "error" | "warning" | "info"; text: string } | null>(null);
  const status = useQuery({
    queryKey: ["gamedata"],
    queryFn: () => api.get<GameDataStatus>("/api/v1/gamedata/status"),
    refetchInterval: (q) => (q.state.data?.update_pending ? POLL_MS : false),
  });
  const sources = useQuery({
    queryKey: ["gamedata-sources"],
    queryFn: () => api.get<{ id: string; name: string; url: string; license: string; role: string }[]>("/api/v1/gamedata/sources"),
  });
  const refresh = () => void client.invalidateQueries({ queryKey: ["gamedata"] });
  const check = useMutation({
    mutationFn: () =>
      api.get<{ available: boolean | null; changed_sources?: string[]; repair_needed?: boolean; error: string | null }>("/api/v1/gamedata/check"),
    onSuccess: (r) =>
      setMessage(
        r.error
          ? { tone: "error", text: r.error }
          : r.repair_needed
            ? { tone: "warning", text: "Het bestand van de actieve versie ontbreekt. Kies Nu bijwerken om het opnieuw op te bouwen." }
            : r.available
            ? { tone: "info", text: `Er is nieuwe data beschikbaar (${(r.changed_sources ?? []).join(", ") || "nog geen actieve versie"}).` }
            : { tone: "success", text: "De actieve versie is actueel." },
      ),
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });
  const update = useMutation({
    mutationFn: () => api.post("/api/v1/gamedata/update"),
    onSuccess: () => {
      setMessage({ tone: "info", text: "Update gestart. OAK downloadt, controleert en activeert de nieuwe versie op de achtergrond." });
      refresh();
    },
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });
  const activate = useMutation({
    mutationFn: (id: number) => api.post(`/api/v1/gamedata/versions/${id}/activate`),
    onSuccess: () => {
      setMessage({ tone: "success", text: "Versie geactiveerd. Analyses worden opnieuw berekend." });
      refresh();
    },
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });
  const upload = useMutation({
    mutationFn: (form: FormData) => api.upload<{ status: string; message: string; warnings: string[] }>("/api/v1/gamedata/upload", form),
    onSuccess: (r) => {
      setMessage({ tone: r.status === "activated" ? "success" : r.status === "failed" ? "error" : "info", text: [r.message, ...r.warnings].join(" ") });
      refresh();
    },
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });

  if (status.isLoading || !status.data) return <Spinner />;
  const s = status.data;
  return (
    <>
      <PageHeader
        title="Game Data"
        description="Spelgegevens met versiebeheer. Een nieuwe versie wordt pas actief na controle. De vorige versies blijven bewaard zodat je terug kunt."
        actions={
          <>
            <Button loading={check.isPending} onClick={() => check.mutate()}>
              Controleren op updates
            </Button>
            {owner && (
              <Button variant="primary" loading={update.isPending || s.update_pending} onClick={() => update.mutate()}>
                Nu bijwerken
              </Button>
            )}
          </>
        }
      />
      {message && (
        <div className="mb-4">
          <Alert tone={message.tone}>{message.text}</Alert>
        </div>
      )}
      {!s.active && (
        <div className="mb-4">
          <Alert tone="warning" title="Geen actieve Game Data">
            Zonder Game Data kan OAK geen soortnamen, levels, PvP-rangen of cleanup-adviezen berekenen. De Pokémon zelf worden wel geïmporteerd.
          </Alert>
        </div>
      )}
      {s.last_error && (
        <div className="mb-4">
          <Alert tone="error" title="Laatste update mislukt">
            {s.last_error} De actieve versie is niet aangeraakt.
          </Alert>
        </div>
      )}
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Actieve versie">
          {s.active ? <Summary version={s.active} /> : <p className="text-sm text-muted">Geen.</p>}
          <p className="mt-3 text-xs text-muted">
            Automatisch bijwerken: {s.auto_update ? `aan, iedere ${s.interval_hours} uur` : "uit"}. Laatste controle: {dateTime(s.last_check?.at)}.
          </p>
        </Card>
        <Card title="Wat ervan afhangt">
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {s.dependent_analyses.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </Card>
        <Card title="Versies">
          <ul className="divide-y divide-line text-sm">
            {s.versions.map((v) => (
              <li key={v.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span>
                  #{v.id} · {dateTime(v.created_at)} · <Badge color={v.status === "active" ? "#22c55e" : v.status === "failed" ? "#ef4444" : undefined}>{statusText[v.status] ?? v.status}</Badge>
                  {v.error && <span className="block text-xs text-red-300">{v.error}</span>}
                </span>
                {owner && ACTIVATABLE.includes(v.status) && (
                  <Button size="sm" loading={activate.isPending} onClick={() => activate.mutate(v.id)}>
                    Activeren
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Bronnen en licenties">
          <ul className="space-y-3 text-sm">
            {sources.data?.map((src) => (
              <li key={src.id}>
                <p className="font-medium">
                  {src.name} <span className="text-xs text-muted">({src.role})</span>
                </p>
                <p className="break-all text-xs text-muted">{src.url}</p>
                <p className="text-xs">Licentie: {src.license}</p>
              </li>
            ))}
          </ul>
          {s.active && (
            <details className="mt-3 text-xs">
              <summary className="cursor-pointer text-muted">Controlegetallen van de actieve versie</summary>
              <ul className="mt-2 space-y-1">
                {s.active.sources.map((src) => (
                  <li key={src.id} className="break-all">
                    {src.id}: {src.sha256?.slice(0, 16)}… · {bytes(src.bytes ?? null)} · opgehaald {dateTime(src.retrieved_at)}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </Card>
        {owner && (
          <Card title="Offline installeren" className="lg:col-span-2">
            <p className="mb-3 text-sm text-muted">
              Heeft de server geen internet, download de bestanden dan elders en upload ze hier. OAK controleert ze op dezelfde manier als een
              download.
            </p>
            <form
              className="grid gap-3 md:grid-cols-2"
              onSubmit={(e) => {
                e.preventDefault();
                upload.mutate(new FormData(e.currentTarget));
              }}
            >
              {UPLOAD_FIELDS.map((f) => (
                <label key={f.name} className="text-sm">
                  <span className="mb-1 block text-muted">
                    {f.label}
                    {f.required && " (verplicht)"}
                  </span>
                  <input type="file" name={f.name} accept=".json,application/json" required={f.required} className="text-xs" />
                </label>
              ))}
              <div className="md:col-span-2">
                <Button type="submit" variant="primary" loading={upload.isPending}>
                  Uploaden en controleren
                </Button>
              </div>
            </form>
          </Card>
        )}
      </div>
    </>
  );
}
