import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { RequireAccount } from "../../components/layout/RequireAccount";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, PageHeader, Spinner } from "../../components/ui";
import { api, errorMessage } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateTime, num, relative } from "../../lib/format";
import { eventKindLabels, label } from "../../lib/i18n";
import { SpeciesPicker, type SpeciesOption } from "../battles/shared";

interface EventItem {
  id: number;
  external_id: string;
  source: string;
  name: string;
  kind: string;
  starts_at: string;
  ends_at: string;
  local_time: boolean;
  link: string | null;
  species: { dex: number; name: string | null }[];
  unknown_names: string[];
  bonuses: string[];
  transfer_bonus: string | null;
  ignored: boolean;
  in_reach: boolean;
  held: number;
}

interface EventsResponse {
  feed: {
    source: string;
    auto_update: boolean;
    version: string | null;
    fetched_at: string | null;
    checked_at: string | null;
    count: number;
    error: string | null;
  };
  rules: { use_events: boolean; event_hold_days: number };
  events: EventItem[];
}

function FeedCard({ data, accountId }: { data: EventsResponse; accountId: number }) {
  const { user } = useAuth();
  const client = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const update = useMutation({
    mutationFn: () => api.post("/api/v1/events/update"),
    onSuccess: () => {
      setMessage("Bijwerken gestart. De eventkalender wordt op de achtergrond opgehaald.");
      window.setTimeout(() => void client.invalidateQueries({ queryKey: ["events", accountId] }), 3000);
    },
    onError: (err) => setMessage(errorMessage(err)),
  });
  const feed = data.feed;
  return (
    <Card className="mb-5">
      <p className="text-sm">
        Eventgegevens: <a href="https://leekduck.com/events/" className="underline hover:text-oak-300">LeekDuck.com</a> via{" "}
        <a href="https://github.com/bigfoott/ScrapedDuck" className="underline hover:text-oak-300">
          ScrapedDuck
        </a>
        . Deze gegevens zijn niet officieel. Controleer bij twijfel het event zelf.
      </p>
      <p className="mt-1 text-xs text-muted">
        {feed.fetched_at ? `Laatst opgehaald ${relative(feed.fetched_at)}, ${num(feed.count)} events, versie ${feed.version}.` : "Nog niet opgehaald."}
        {feed.auto_update ? " OAK werkt de kalender automatisch bij." : " Automatisch bijwerken staat uit."}
      </p>
      {feed.error && (
        <div className="mt-3">
          <Alert tone="warning">Laatste poging om bij te werken mislukte: {feed.error} De vorige events blijven gelden.</Alert>
        </div>
      )}
      {!data.rules.use_events && (
        <div className="mt-3">
          <Alert tone="info">
            Events tellen niet mee in je cleanupadvies. Zet dat aan bij de{" "}
            <Link to="/cleanup?tab=rules" className="underline">
              Cleanup-regels
            </Link>
            .
          </Alert>
        </div>
      )}
      {user?.role === "owner" && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button size="sm" loading={update.isPending} onClick={() => update.mutate()}>
            Nu bijwerken
          </Button>
          {message && <span className="text-xs text-muted">{message}</span>}
        </div>
      )}
    </Card>
  );
}

/** Whether the cleanup rules can do anything with this event. */
function hasEffect(event: EventItem): boolean {
  if (event.kind === "community-day" || event.kind === "manual") return event.species.length > 0;
  return Boolean(event.transfer_bonus);
}

function EventRow({ event, accountId, rules }: { event: EventItem; accountId: number; rules: EventsResponse["rules"] }) {
  const client = useQueryClient();
  const refresh = () => void client.invalidateQueries({ queryKey: ["events", accountId] });
  const ignore = useMutation({
    mutationFn: (ignored: boolean) => api.put(`/api/v1/events/${encodeURIComponent(event.external_id)}/ignore`, { account_id: accountId, ignored }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: () => api.delete(`/api/v1/events/manual/${event.id}`, undefined, { account_id: accountId }),
    onSuccess: refresh,
  });
  const manual = event.kind === "manual";
  const effect = hasEffect(event);
  return (
    <li className="flex flex-wrap items-start justify-between gap-3 py-3">
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{event.name}</span>
          <Badge>{label(eventKindLabels, event.kind)}</Badge>
          {event.in_reach && effect && <Badge color="#22c55e">Telt mee</Badge>}
          {event.ignored && <Badge color="#94a3b8">Genegeerd</Badge>}
          {event.link && (
            <a href={event.link} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink">
              Details <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </p>
        <p className="text-xs text-muted">
          {dateTime(event.starts_at)} tot {dateTime(event.ends_at)}
          {event.local_time ? " (lokale tijd)" : ""} · {event.source}
        </p>
        {event.species.length > 0 && <p className="mt-1 text-xs">Pokémon: {event.species.map((s) => s.name ?? `#${s.dex}`).join(", ")}</p>}
        {event.unknown_names.length > 0 && (
          <p className="mt-1 text-xs text-amber-300">Niet in de Game Data gevonden: {event.unknown_names.join(", ")}. Daarvoor bewaart OAK niets.</p>
        )}
        {event.bonuses.length > 0 && <p className="mt-1 text-xs text-muted">Bonussen: {event.bonuses.join(" · ")}</p>}
        {event.held > 0 && (
          <p className="mt-1 text-xs text-oak-300">
            OAK bewaart hiervoor {num(event.held)} van je Pokémon tot na het event.{" "}
            <Link to="/cleanup?status=KEEP" className="underline">
              Bekijk in de Cleanup Manager
            </Link>
          </p>
        )}
        {event.transfer_bonus && event.in_reach && (
          <p className="mt-1 text-xs text-oak-300">Tip: zet transfer-kandidaten pas tijdens dit event over ({event.transfer_bonus}).</p>
        )}
        {rules.use_events && effect && !event.in_reach && !event.ignored && (
          <p className="mt-1 text-xs text-muted">Telt mee vanaf {rules.event_hold_days} dagen voor het begin.</p>
        )}
      </div>
      {manual ? (
        <Button size="sm" variant="ghost" loading={remove.isPending} onClick={() => remove.mutate()}>
          Verwijderen
        </Button>
      ) : (
        <Button size="sm" variant="ghost" loading={ignore.isPending} onClick={() => ignore.mutate(!event.ignored)}>
          {event.ignored ? "Weer meetellen" : "Negeren"}
        </Button>
      )}
    </li>
  );
}

function ManualEventCard({ accountId }: { accountId: number }) {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [species, setSpecies] = useState<SpeciesOption[]>([]);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const add = useMutation({
    mutationFn: () =>
      api.post("/api/v1/events/manual", {
        account_id: accountId,
        name,
        starts_at: new Date(start).toISOString(),
        ends_at: new Date(end).toISOString(),
        species: species.map((s) => s.dex),
      }),
    onSuccess: () => {
      setName("");
      setStart("");
      setEnd("");
      setSpecies([]);
      setMessage({ tone: "success", text: "Event toegevoegd. OAK berekent je cleanupadvies opnieuw." });
      void client.invalidateQueries({ queryKey: ["events", accountId] });
    },
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });
  const valid = name.trim() && start && end && species.length > 0;
  return (
    <Card title="Eigen event toevoegen">
      <p className="mb-3 text-sm text-muted">
        Voor iets dat niet in de kalender staat, zoals een ruilafspraak. OAK bewaart de gekozen Pokémon en hun evolutielijn tot het event voorbij is.
      </p>
      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) add.mutate();
        }}
      >
        <div className="sm:col-span-2">
          <Field label="Naam">
            <Input value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
          </Field>
        </div>
        <Field label="Begin">
          <Input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} />
        </Field>
        <Field label="Einde">
          <Input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
        </Field>
        <div className="sm:col-span-2">
          <SpeciesPicker onPick={(option) => setSpecies((current) => (current.some((s) => s.dex === option.dex) ? current : [...current, option]))} placeholder="Pokémon zoeken, bijv. eevee" />
          {species.length > 0 && (
            <p className="mt-2 flex flex-wrap gap-2">
              {species.map((s) => (
                <button key={s.dex} type="button" className="rounded-full border border-line px-2 py-0.5 text-xs hover:bg-surface-3" onClick={() => setSpecies((current) => current.filter((c) => c.dex !== s.dex))}>
                  {s.name} ×
                </button>
              ))}
            </p>
          )}
        </div>
        <div className="sm:col-span-2">
          <Button type="submit" variant="primary" loading={add.isPending} disabled={!valid}>
            Toevoegen
          </Button>
        </div>
      </form>
      {message && (
        <div className="mt-3">
          <Alert tone={message.tone}>{message.text}</Alert>
        </div>
      )}
    </Card>
  );
}

function Events({ accountId }: { accountId: number }) {
  const query = useQuery({
    queryKey: ["events", accountId],
    queryFn: () => api.get<EventsResponse>("/api/v1/events", { account_id: accountId }),
  });
  const data = query.data;
  return (
    <>
      <PageHeader
        title="Komende events"
        description="Events in de komende 60 dagen. Een Community Day houdt transfer-kandidaten uit die evolutielijn tot na het event vast, en bij dubbele Transfer Candy krijg je een tip om te wachten."
      />
      {query.isLoading && <Spinner />}
      {query.error && <Alert tone="error">{errorMessage(query.error)}</Alert>}
      {data && (
        <>
          <FeedCard data={data} accountId={accountId} />
          <Card className="mb-5" title="Kalender">
            {data.events.length === 0 ? (
              <EmptyState title="Geen events gevonden">Er staan geen events in de komende 60 dagen.</EmptyState>
            ) : (
              <ul className="divide-y divide-line">
                {data.events.map((event) => (
                  <EventRow key={event.id} event={event} accountId={accountId} rules={data.rules} />
                ))}
              </ul>
            )}
          </Card>
          <ManualEventCard accountId={accountId} />
        </>
      )}
    </>
  );
}

export function EventsPage() {
  return <RequireAccount>{(id) => <Events accountId={id} />}</RequireAccount>;
}
