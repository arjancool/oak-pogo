import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { Alert, Badge, Button, Card, Checkbox, Dialog, Field, Input, KeyValue, PageHeader, Select } from "../../components/ui";
import { useAccount } from "../../lib/account";
import { useAuth } from "../../lib/auth";
import { api, errorMessage } from "../../lib/api";
import { bytes, dateTime, num } from "../../lib/format";
import { useAppSettings } from "../../lib/settings";
import type { AppSettings, Facets, User } from "../../lib/types";

type Message = { tone: "success" | "error"; text: string } | null;

function Feedback({ message }: { message: Message }) {
  if (!message) return null;
  return (
    <div className="mt-3">
      <Alert tone={message.tone}>{message.text}</Alert>
    </div>
  );
}

function SpriteSettings({ owner }: { owner: boolean }) {
  const client = useQueryClient();
  const settings = useAppSettings();
  const [source, setSource] = useState<AppSettings["sprite_source"] | null>(null);
  const [template, setTemplate] = useState<string | null>(null);
  const [message, setMessage] = useState<Message>(null);
  const current = settings.data;
  const chosen = source ?? current?.sprite_source ?? "none";
  const save = useMutation({
    mutationFn: () => api.put("/api/v1/settings", { sprite_source: chosen, sprite_url_template: template ?? current?.sprite_url_template }),
    onSuccess: () => {
      setMessage({ tone: "success", text: "Opgeslagen. Herlaad de pagina om de nieuwe beveiligingsinstellingen voor afbeeldingen te gebruiken." });
      void client.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });
  return (
    <Card title="Pokémon-afbeeldingen">
      <Alert tone="info">{current?.sprite_notice}</Alert>
      <div className="mt-3 grid gap-3">
        <Field label="Bron">
          <Select value={chosen} disabled={!owner} onChange={(e) => setSource(e.target.value as AppSettings["sprite_source"])}>
            <option value="none">Geen afbeeldingen (dexnummer en typekleur)</option>
            <option value="pokeapi">PokeAPI sprites via GitHub</option>
            <option value="custom">Eigen bron</option>
          </Select>
        </Field>
        {chosen === "custom" && (
          <Field label="URL-sjabloon" hint="Moet met https:// beginnen en {dex} bevatten. {shiny_path} wordt 'shiny/' voor shiny Pokémon.">
            <Input value={template ?? current?.sprite_url_template ?? ""} disabled={!owner} onChange={(e) => setTemplate(e.target.value)} placeholder="https://example.org/sprites/{shiny_path}{dex}.png" />
          </Field>
        )}
      </div>
      {owner ? (
        <Button className="mt-3" variant="primary" loading={save.isPending} onClick={() => save.mutate()}>
          Opslaan
        </Button>
      ) : (
        <p className="mt-3 text-xs text-muted">Alleen de eigenaar kan dit wijzigen.</p>
      )}
      <Feedback message={message} />
    </Card>
  );
}

function TagSettings({ accountId }: { accountId: number }) {
  const client = useQueryClient();
  const facets = useQuery({ queryKey: ["facets", accountId], queryFn: () => api.get<Facets>("/api/v1/pokemon/facets", { account_id: accountId }) });
  const [drafts, setDrafts] = useState<Record<string, { label: string; protects: boolean }>>({});
  const [message, setMessage] = useState<Message>(null);
  const save = useMutation({
    mutationFn: (body: { tag_id: string; label: string; protects: boolean }) => api.put("/api/v1/pokemon/tags/labels", { account_id: accountId, ...body }),
    onSuccess: () => {
      setMessage({ tone: "success", text: "Tag opgeslagen. De cleanup-analyse wordt opnieuw berekend." });
      void client.invalidateQueries({ queryKey: ["facets"] });
    },
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });
  const tags = facets.data?.tags ?? [];
  return (
    <Card title="In-game tags">
      <p className="mb-3 text-sm text-muted">
        PGSharp exporteert alleen het nummer van een tag, niet de naam. Geef je tags hier een naam en kies welke tags een Pokémon beschermen tegen
        cleanup-advies.
      </p>
      {tags.length === 0 ? (
        <p className="text-sm text-muted">Geen tags gevonden in de laatste import.</p>
      ) : (
        <ul className="space-y-2">
          {tags.map((tag) => {
            const draft = drafts[tag.tag_id] ?? { label: tag.label ?? "", protects: tag.protects };
            const set = (next: Partial<typeof draft>) => setDrafts({ ...drafts, [tag.tag_id]: { ...draft, ...next } });
            return (
              <li key={tag.tag_id} className="flex flex-wrap items-center gap-3">
                <Badge title={tag.tag_id}>{num(tag.count)} Pokémon</Badge>
                <Input value={draft.label} placeholder={`Tag …${tag.tag_id.slice(-4)}`} maxLength={64} onChange={(e) => set({ label: e.target.value })} className="w-56" aria-label="Naam van de tag" />
                <Checkbox checked={draft.protects} onChange={(value) => set({ protects: value })} label="Beschermt" />
                <Button size="sm" disabled={!draft.label.trim()} onClick={() => save.mutate({ tag_id: tag.tag_id, label: draft.label.trim(), protects: draft.protects })}>
                  Opslaan
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      <Feedback message={message} />
    </Card>
  );
}

function PasswordSettings() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [message, setMessage] = useState<Message>(null);
  const change = useMutation({
    mutationFn: () => api.post("/api/v1/auth/change-password", { current_password: current, new_password: next }),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      setMessage({ tone: "success", text: "Wachtwoord gewijzigd. Andere sessies zijn afgemeld." });
    },
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });
  return (
    <Card title="Wachtwoord wijzigen">
      <form
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          change.mutate();
        }}
      >
        <Field label="Huidig wachtwoord">
          <Input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
        </Field>
        <Field label="Nieuw wachtwoord" hint="Minimaal 10 tekens.">
          <Input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
        </Field>
        <div>
          <Button type="submit" variant="primary" loading={change.isPending} disabled={!current || !next}>
            Wijzigen
          </Button>
        </div>
      </form>
      <Feedback message={message} />
    </Card>
  );
}

const MIN_PASSWORD_LENGTH = 10;

/** The owner sets a new password for another user. Every session of that user ends. */
function ResetPasswordDialog({ user, onClose, onDone }: { user: User; onClose: () => void; onDone: (text: string) => void }) {
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const reset = useMutation({
    mutationFn: () => api.patch(`/api/v1/users/${user.id}`, { password }),
    onSuccess: () => onDone(`Nieuw wachtwoord ingesteld voor ${user.username}. Die is overal uitgelogd en logt in met het nieuwe wachtwoord.`),
  });
  const tooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH;
  const mismatch = repeat.length > 0 && repeat !== password;
  const valid = password.length >= MIN_PASSWORD_LENGTH && password === repeat;
  return (
    <Dialog
      open
      onClose={onClose}
      title={`Wachtwoord van ${user.username} opnieuw instellen`}
      footer={
        <>
          <Button onClick={onClose}>Annuleren</Button>
          <Button variant="primary" loading={reset.isPending} disabled={!valid} onClick={() => reset.mutate()}>
            Opnieuw instellen
          </Button>
        </>
      }
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) reset.mutate();
        }}
      >
        <p className="text-sm text-muted">
          Geef de gebruiker het nieuwe wachtwoord via een veilige weg. Daarna kan die het zelf wijzigen onder Instellingen. Alle sessies van deze gebruiker
          eindigen meteen.
        </p>
        <Field label="Nieuw wachtwoord" hint={tooShort ? `Minimaal ${MIN_PASSWORD_LENGTH} tekens.` : undefined}>
          <Input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
        </Field>
        <Field label="Herhaal nieuw wachtwoord" hint={mismatch ? "De wachtwoorden zijn niet gelijk." : undefined}>
          <Input type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} />
        </Field>
        {reset.error && <Alert tone="error">{errorMessage(reset.error)}</Alert>}
      </form>
    </Dialog>
  );
}

function UserSettings() {
  const client = useQueryClient();
  const { user: me } = useAuth();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.get<User[]>("/api/v1/users") });
  const [form, setForm] = useState({ username: "", password: "" });
  const [message, setMessage] = useState<Message>(null);
  const [resetting, setResetting] = useState<User | null>(null);
  const refresh = () => void client.invalidateQueries({ queryKey: ["users"] });
  const create = useMutation({
    mutationFn: () => api.post("/api/v1/users", form),
    onSuccess: () => {
      setForm({ username: "", password: "" });
      setMessage({ tone: "success", text: "Gebruiker aangemaakt." });
      refresh();
    },
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });
  const toggle = useMutation({
    mutationFn: (u: User) => api.patch(`/api/v1/users/${u.id}`, { status: u.status === "active" ? "disabled" : "active" }),
    onSuccess: refresh,
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });
  return (
    <Card title="Gebruikers">
      <ul className="mb-4 divide-y divide-line text-sm">
        {users.data?.map((u) => (
          <li key={u.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span>
              {u.username} {u.role === "owner" && <Badge>eigenaar</Badge>} {u.status !== "active" && <Badge color="#ef4444">uitgeschakeld</Badge>}
              <span className="block text-xs text-muted">Laatst ingelogd: {dateTime(u.last_login_at)}</span>
            </span>
            {u.id !== me?.id && (
              <span className="flex flex-wrap gap-2">
                <Button size="sm" onClick={() => setResetting(u)}>
                  Wachtwoord opnieuw instellen
                </Button>
                <Button size="sm" onClick={() => toggle.mutate(u)}>
                  {u.status === "active" ? "Uitschakelen" : "Inschakelen"}
                </Button>
              </span>
            )}
          </li>
        ))}
      </ul>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <Field label="Gebruikersnaam">
          <Input value={form.username} autoComplete="off" onChange={(e) => setForm({ ...form, username: e.target.value })} />
        </Field>
        <Field label="Wachtwoord">
          <Input type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </Field>
        <Button type="submit" loading={create.isPending} disabled={!form.username || !form.password}>
          Toevoegen
        </Button>
      </form>
      <p className="mt-2 text-xs text-muted">
        Iedere gebruiker ziet alleen zijn eigen traineraccounts. Je eigen wachtwoord wijzig je bij Wachtwoord wijzigen, met je huidige wachtwoord.
      </p>
      <Feedback message={message} />
      {resetting && (
        <ResetPasswordDialog
          user={resetting}
          onClose={() => setResetting(null)}
          onDone={(text) => {
            setResetting(null);
            setMessage({ tone: "success", text });
          }}
        />
      )}
    </Card>
  );
}

interface SystemStatus {
  version: string;
  build: Record<string, string | null>;
  started_at: string;
  timezone: string;
  base_url: string;
  database: { size_bytes: number };
  storage: { total_bytes: number; free_bytes: number };
  jobs: { pending: number; failed: number };
  failed_imports: number;
  last_successful_sync: string | null;
  game_data: { version_id: number | null };
  secret_key_source: string;
  registration_open: boolean;
  raw_import_retention_days: number;
  worker_running: boolean;
}

function SystemCard() {
  const status = useQuery({ queryKey: ["system-status"], queryFn: () => api.get<SystemStatus>("/api/v1/system/status") });
  const s = status.data;
  if (!s) return null;
  return (
    <Card title="Systeem">
      <KeyValue
        items={[
          ["Versie", `${s.version}${s.build.sha ? ` (${s.build.sha.slice(0, 7)})` : ""}`],
          ["Gestart", dateTime(s.started_at)],
          ["Tijdzone", s.timezone],
          ["Basis-URL", s.base_url],
          ["Database", bytes(s.database.size_bytes)],
          ["Vrije schijfruimte", `${bytes(s.storage.free_bytes)} van ${bytes(s.storage.total_bytes)}`],
          ["Achtergrondtaken", `${s.jobs.pending} bezig · ${s.jobs.failed} mislukt`],
          ["Mislukte imports", num(s.failed_imports)],
          ["Laatste succesvolle sync", dateTime(s.last_successful_sync)],
          ["Game Data-versie", s.game_data.version_id ? `#${s.game_data.version_id}` : "geen"],
          ["Geheime sleutel", s.secret_key_source === "generated" ? "automatisch aangemaakt in /data" : "uit omgevingsvariabele"],
          ["Registratie", s.registration_open ? "open" : "gesloten"],
          ["Exports bewaren", `${s.raw_import_retention_days} dagen`],
          ["Achtergrondverwerking", s.worker_running ? "actief" : "uit"],
        ]}
      />
    </Card>
  );
}

export function SettingsPage() {
  const { user } = useAuth();
  const { accountId } = useAccount();
  const owner = user?.role === "owner";
  return (
    <>
      <PageHeader title="Instellingen" />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Cleanup-regels">
          <p className="text-sm text-muted">
            Favorieten krijgen extra bewaarpunten maar geen harde bescherming. Pokémon uit 2016 tot en met 2019 zijn altijd beschermd als
            vintage. Gewichten, drempels en de overige beschermingsregels stel je per traineraccount in.
          </p>
          <Link to="/cleanup?tab=rules" className="mt-3 inline-block">
            <Button>Cleanup-regels openen</Button>
          </Link>
        </Card>
        <SpriteSettings owner={owner} />
        {accountId !== null && <TagSettings accountId={accountId} />}
        <PasswordSettings />
        {owner && <UserSettings />}
        {owner && <SystemCard />}
      </div>
    </>
  );
}
