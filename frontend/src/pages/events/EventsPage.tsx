import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { useState } from "react";
import { Trans, useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
  const { user } = useAuth();
  const client = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const update = useMutation({
    mutationFn: () => api.post("/api/v1/events/update"),
    onSuccess: () => {
      setMessage(t("events.feed.updateStarted"));
      window.setTimeout(() => void client.invalidateQueries({ queryKey: ["events", accountId] }), 3000);
    },
    onError: (err) => setMessage(errorMessage(err)),
  });
  const feed = data.feed;
  return (
    <Card className="mb-5">
      <p className="text-sm">
        <Trans
          i18nKey="events.feed.source"
          components={{
            leekduck: <a href="https://leekduck.com/events/" className="underline hover:text-oak-300" />,
            scrapedduck: <a href="https://github.com/bigfoott/ScrapedDuck" className="underline hover:text-oak-300" />,
          }}
        />
      </p>
      <p className="mt-1 text-xs text-muted">
        {feed.fetched_at
          ? t("events.feed.fetched", { count: feed.count, n: num(feed.count), when: relative(feed.fetched_at), version: feed.version })
          : t("events.feed.notFetched")}{" "}
        {feed.auto_update ? t("events.feed.autoOn") : t("events.feed.autoOff")}
      </p>
      {feed.error && (
        <div className="mt-3">
          <Alert tone="warning">{t("events.feed.failed", { error: feed.error })}</Alert>
        </div>
      )}
      {!data.rules.use_events && (
        <div className="mt-3">
          <Alert tone="info">
            <Trans i18nKey="events.feed.notUsed" components={{ rulesLink: <Link to="/cleanup?tab=rules" className="underline" /> }} />
          </Alert>
        </div>
      )}
      {user?.role === "owner" && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button size="sm" loading={update.isPending} onClick={() => update.mutate()}>
            {t("events.feed.updateNow")}
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
  const { t } = useTranslation();
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
          {event.in_reach && effect && <Badge color="#22c55e">{t("events.row.counts")}</Badge>}
          {event.ignored && <Badge color="#94a3b8">{t("events.row.ignored")}</Badge>}
          {event.link && (
            <a href={event.link} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink">
              {t("events.row.details")} <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </p>
        <p className="text-xs text-muted">
          {t(event.local_time ? "events.row.periodLocal" : "events.row.period", { start: dateTime(event.starts_at), end: dateTime(event.ends_at) })} ·{" "}
          {event.source}
        </p>
        {event.species.length > 0 && (
          <p className="mt-1 text-xs">{t("events.row.species", { names: event.species.map((s) => s.name ?? `#${s.dex}`).join(", ") })}</p>
        )}
        {event.unknown_names.length > 0 && (
          <p className="mt-1 text-xs text-amber-300">{t("events.row.unknownNames", { names: event.unknown_names.join(", ") })}</p>
        )}
        {event.bonuses.length > 0 && <p className="mt-1 text-xs text-muted">{t("events.row.bonuses", { bonuses: event.bonuses.join(" · ") })}</p>}
        {event.held > 0 && (
          <p className="mt-1 text-xs text-oak-300">
            <Trans
              i18nKey="events.row.held"
              values={{ n: num(event.held) }}
              components={{ cleanupLink: <Link to="/cleanup?status=KEEP" className="underline" /> }}
            />
          </p>
        )}
        {event.transfer_bonus && event.in_reach && (
          <p className="mt-1 text-xs text-oak-300">{t("events.row.transferTip", { bonus: event.transfer_bonus })}</p>
        )}
        {rules.use_events && effect && !event.in_reach && !event.ignored && (
          <p className="mt-1 text-xs text-muted">{t("events.row.countsFrom", { count: rules.event_hold_days })}</p>
        )}
      </div>
      {manual ? (
        <Button size="sm" variant="ghost" loading={remove.isPending} onClick={() => remove.mutate()}>
          {t("events.row.remove")}
        </Button>
      ) : (
        <Button size="sm" variant="ghost" loading={ignore.isPending} onClick={() => ignore.mutate(!event.ignored)}>
          {event.ignored ? t("events.row.include") : t("events.row.ignore")}
        </Button>
      )}
    </li>
  );
}

function ManualEventCard({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
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
      setMessage({ tone: "success", text: t("events.manual.added") });
      void client.invalidateQueries({ queryKey: ["events", accountId] });
    },
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });
  const valid = name.trim() && start && end && species.length > 0;
  return (
    <Card title={t("events.manual.title")}>
      <p className="mb-3 text-sm text-muted">{t("events.manual.intro")}</p>
      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) add.mutate();
        }}
      >
        <div className="sm:col-span-2">
          <Field label={t("events.manual.name")}>
            <Input value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
          </Field>
        </div>
        <Field label={t("events.manual.start")}>
          <Input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} />
        </Field>
        <Field label={t("events.manual.end")}>
          <Input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
        </Field>
        <div className="sm:col-span-2">
          <SpeciesPicker onPick={(option) => setSpecies((current) => (current.some((s) => s.dex === option.dex) ? current : [...current, option]))} placeholder={t("events.manual.species")} />
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
            {t("events.manual.add")}
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
  const { t } = useTranslation();
  const query = useQuery({
    queryKey: ["events", accountId],
    queryFn: () => api.get<EventsResponse>("/api/v1/events", { account_id: accountId }),
  });
  const data = query.data;
  return (
    <>
      <PageHeader title={t("events.title")} description={t("events.description")} />
      {query.isLoading && <Spinner />}
      {query.error && <Alert tone="error">{errorMessage(query.error)}</Alert>}
      {data && (
        <>
          <FeedCard data={data} accountId={accountId} />
          <Card className="mb-5" title={t("events.calendar")}>
            {data.events.length === 0 ? (
              <EmptyState title={t("events.emptyTitle")}>{t("events.emptyText")}</EmptyState>
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
