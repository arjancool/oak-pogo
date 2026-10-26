import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { Alert, Badge, Button, Card, Checkbox, Dialog, Field, Input, KeyValue, PageHeader, Select } from "../../components/ui";
import { useAccount } from "../../lib/account";
import { useAuth } from "../../lib/auth";
import { api, errorMessage } from "../../lib/api";
import { bytes, dateTime, num } from "../../lib/format";
import { serverText } from "../../lib/serverText";
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
  const { t } = useTranslation();
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
      setMessage({ tone: "success", text: t("admin.settings.sprites.saved") });
      void client.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });
  return (
    <Card title={t("admin.settings.sprites.title")}>
      <Alert tone="info">{serverText("gamedata", current?.sprite_notice)}</Alert>
      <div className="mt-3 grid gap-3">
        <Field label={t("admin.settings.sprites.source")}>
          <Select value={chosen} disabled={!owner} onChange={(e) => setSource(e.target.value as AppSettings["sprite_source"])}>
            <option value="none">{t("admin.settings.sprites.none")}</option>
            <option value="pokeapi">{t("admin.settings.sprites.pokeapi")}</option>
            <option value="custom">{t("admin.settings.sprites.custom")}</option>
          </Select>
        </Field>
        {chosen === "custom" && (
          <Field label={t("admin.settings.sprites.template")} hint={t("admin.settings.sprites.templateHint")}>
            <Input value={template ?? current?.sprite_url_template ?? ""} disabled={!owner} onChange={(e) => setTemplate(e.target.value)} placeholder="https://example.org/sprites/{shiny_path}{dex}.png" />
          </Field>
        )}
      </div>
      {owner ? (
        <Button className="mt-3" variant="primary" loading={save.isPending} onClick={() => save.mutate()}>
          {t("admin.settings.save")}
        </Button>
      ) : (
        <p className="mt-3 text-xs text-muted">{t("admin.settings.sprites.ownerOnly")}</p>
      )}
      <Feedback message={message} />
    </Card>
  );
}

function TagSettings({ accountId }: { accountId: number }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const facets = useQuery({ queryKey: ["facets", accountId], queryFn: () => api.get<Facets>("/api/v1/pokemon/facets", { account_id: accountId }) });
  const [drafts, setDrafts] = useState<Record<string, { label: string; protects: boolean }>>({});
  const [message, setMessage] = useState<Message>(null);
  const save = useMutation({
    mutationFn: (body: { tag_id: string; label: string; protects: boolean }) => api.put("/api/v1/pokemon/tags/labels", { account_id: accountId, ...body }),
    onSuccess: () => {
      setMessage({ tone: "success", text: t("admin.settings.tags.saved") });
      void client.invalidateQueries({ queryKey: ["facets"] });
    },
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });
  const tags = facets.data?.tags ?? [];
  return (
    <Card title={t("admin.settings.tags.title")}>
      <p className="mb-3 text-sm text-muted">{t("admin.settings.tags.intro")}</p>
      {tags.length === 0 ? (
        <p className="text-sm text-muted">{t("admin.settings.tags.none")}</p>
      ) : (
        <ul className="space-y-2">
          {tags.map((tag) => {
            const draft = drafts[tag.tag_id] ?? { label: tag.label ?? "", protects: tag.protects };
            const set = (next: Partial<typeof draft>) => setDrafts({ ...drafts, [tag.tag_id]: { ...draft, ...next } });
            return (
              <li key={tag.tag_id} className="flex flex-wrap items-center gap-3">
                <Badge title={tag.tag_id}>{num(tag.count)} Pokémon</Badge>
                <Input value={draft.label} placeholder={`Tag …${tag.tag_id.slice(-4)}`} maxLength={64} onChange={(e) => set({ label: e.target.value })} className="w-56" aria-label={t("admin.settings.tags.name")} />
                <Checkbox checked={draft.protects} onChange={(value) => set({ protects: value })} label={t("admin.settings.tags.protects")} />
                <Button size="sm" disabled={!draft.label.trim()} onClick={() => save.mutate({ tag_id: tag.tag_id, label: draft.label.trim(), protects: draft.protects })}>
                  {t("admin.settings.save")}
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
  const { t } = useTranslation();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [message, setMessage] = useState<Message>(null);
  const change = useMutation({
    mutationFn: () => api.post("/api/v1/auth/change-password", { current_password: current, new_password: next }),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      setMessage({ tone: "success", text: t("admin.settings.password.changed") });
    },
    onError: (err) => setMessage({ tone: "error", text: errorMessage(err) }),
  });
  return (
    <Card title={t("admin.settings.password.title")}>
      <form
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          change.mutate();
        }}
      >
        <Field label={t("admin.settings.password.current")}>
          <Input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
        </Field>
        <Field label={t("admin.settings.password.new")} hint={t("admin.settings.password.minLength", { length: num(MIN_PASSWORD_LENGTH) })}>
          <Input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
        </Field>
        <div>
          <Button type="submit" variant="primary" loading={change.isPending} disabled={!current || !next}>
            {t("admin.settings.password.submit")}
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
  const { t } = useTranslation();
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const reset = useMutation({
    mutationFn: () => api.patch(`/api/v1/users/${user.id}`, { password }),
    onSuccess: () => onDone(t("admin.settings.reset.done", { name: user.username })),
  });
  const tooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH;
  const mismatch = repeat.length > 0 && repeat !== password;
  const valid = password.length >= MIN_PASSWORD_LENGTH && password === repeat;
  return (
    <Dialog
      open
      onClose={onClose}
      title={t("admin.settings.reset.title", { name: user.username })}
      footer={
        <>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button variant="primary" loading={reset.isPending} disabled={!valid} onClick={() => reset.mutate()}>
            {t("admin.settings.reset.submit")}
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
        <p className="text-sm text-muted">{t("admin.settings.reset.text")}</p>
        <Field label={t("admin.settings.password.new")} hint={tooShort ? t("admin.settings.password.minLength", { length: num(MIN_PASSWORD_LENGTH) }) : undefined}>
          <Input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
        </Field>
        <Field label={t("admin.settings.reset.repeat")} hint={mismatch ? t("admin.settings.reset.mismatch") : undefined}>
          <Input type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} />
        </Field>
        {reset.error && <Alert tone="error">{errorMessage(reset.error)}</Alert>}
      </form>
    </Dialog>
  );
}

function UserSettings() {
  const { t } = useTranslation();
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
      setMessage({ tone: "success", text: t("admin.settings.users.created") });
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
    <Card title={t("admin.settings.users.title")}>
      <ul className="mb-4 divide-y divide-line text-sm">
        {users.data?.map((u) => (
          <li key={u.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span>
              {u.username} {u.role === "owner" && <Badge>{t("admin.settings.users.owner")}</Badge>} {u.status !== "active" && <Badge color="#ef4444">{t("admin.settings.users.disabled")}</Badge>}
              <span className="block text-xs text-muted">{t("admin.settings.users.lastLogin", { date: dateTime(u.last_login_at) })}</span>
            </span>
            {u.id !== me?.id && (
              <span className="flex flex-wrap gap-2">
                <Button size="sm" onClick={() => setResetting(u)}>
                  {t("admin.settings.users.resetPassword")}
                </Button>
                <Button size="sm" onClick={() => toggle.mutate(u)}>
                  {u.status === "active" ? t("admin.settings.users.disable") : t("admin.settings.users.enable")}
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
        <Field label={t("admin.settings.users.username")}>
          <Input value={form.username} autoComplete="off" onChange={(e) => setForm({ ...form, username: e.target.value })} />
        </Field>
        <Field label={t("admin.settings.users.password")}>
          <Input type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </Field>
        <Button type="submit" loading={create.isPending} disabled={!form.username || !form.password}>
          {t("admin.settings.users.add")}
        </Button>
      </form>
      <p className="mt-2 text-xs text-muted">{t("admin.settings.users.note")}</p>
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
  const { t } = useTranslation();
  const status = useQuery({ queryKey: ["system-status"], queryFn: () => api.get<SystemStatus>("/api/v1/system/status") });
  const s = status.data;
  if (!s) return null;
  return (
    <Card title={t("admin.settings.system.title")}>
      <KeyValue
        items={[
          [t("admin.settings.system.version"), `${s.version}${s.build.sha ? ` (${s.build.sha.slice(0, 7)})` : ""}`],
          [t("admin.settings.system.started"), dateTime(s.started_at)],
          [t("admin.settings.system.timezone"), s.timezone],
          [t("admin.settings.system.baseUrl"), s.base_url],
          [t("admin.settings.system.database"), bytes(s.database.size_bytes)],
          [t("admin.settings.system.freeSpace"), t("admin.settings.system.freeSpaceValue", { free: bytes(s.storage.free_bytes), total: bytes(s.storage.total_bytes) })],
          [t("admin.settings.system.jobs"), t("admin.settings.system.jobsValue", { pending: num(s.jobs.pending), failed: num(s.jobs.failed) })],
          [t("admin.settings.system.failedImports"), num(s.failed_imports)],
          [t("admin.settings.system.lastSync"), dateTime(s.last_successful_sync)],
          [t("admin.settings.system.gameData"), s.game_data.version_id ? `#${s.game_data.version_id}` : t("admin.settings.system.gameDataNone")],
          [t("admin.settings.system.secretKey"), s.secret_key_source === "generated" ? t("admin.settings.system.secretGenerated") : t("admin.settings.system.secretEnvironment")],
          [t("admin.settings.system.registration"), s.registration_open ? t("admin.settings.system.registrationOpen") : t("admin.settings.system.registrationClosed")],
          [t("admin.settings.system.retention"), t("admin.settings.system.retentionValue", { count: s.raw_import_retention_days, days: num(s.raw_import_retention_days) })],
          [t("admin.settings.system.worker"), s.worker_running ? t("admin.settings.system.workerOn") : t("admin.settings.system.workerOff")],
        ]}
      />
    </Card>
  );
}

export function SettingsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { accountId } = useAccount();
  const owner = user?.role === "owner";
  return (
    <>
      <PageHeader title={t("admin.settings.title")} />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title={t("admin.settings.rules.title")}>
          <p className="text-sm text-muted">{t("admin.settings.rules.text")}</p>
          <Link to="/cleanup?tab=rules" className="mt-3 inline-block">
            <Button>{t("admin.settings.rules.open")}</Button>
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
