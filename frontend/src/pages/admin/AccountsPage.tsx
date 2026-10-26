import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Link } from "react-router";

import { Alert, Badge, Button, Card, Dialog, EmptyState, Field, Input, KeyValue, PageHeader } from "../../components/ui";
import { useAccount } from "../../lib/account";
import { api, errorMessage } from "../../lib/api";
import { dateTime, num } from "../../lib/format";
import type { Account } from "../../lib/types";

const DEFAULT_DROP_FRACTION = 0.2;
const DEFAULT_DROP_ABSOLUTE = 25;
const PERCENT = 100;

function AccountCard({ account }: { account: Account }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const { setAccountId, accountId } = useAccount();
  const [nickname, setNickname] = useState(account.nickname);
  const [fraction, setFraction] = useState(Math.round((account.completeness.max_drop_fraction ?? DEFAULT_DROP_FRACTION) * PERCENT));
  const [absolute, setAbsolute] = useState(account.completeness.max_drop_absolute ?? DEFAULT_DROP_ABSOLUTE);
  const [deleting, setDeleting] = useState(false);
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const refresh = () => void client.invalidateQueries({ queryKey: ["accounts"] });

  const save = useMutation({
    mutationFn: () =>
      api.patch(`/api/v1/accounts/${account.id}`, {
        nickname,
        completeness: { max_drop_fraction: fraction / PERCENT, max_drop_absolute: absolute },
      }),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (err) => setError(errorMessage(err)),
  });
  const unlink = useMutation({ mutationFn: () => api.post(`/api/v1/accounts/${account.id}/unlink`), onSuccess: refresh, onError: (err) => setError(errorMessage(err)) });
  const remove = useMutation({
    mutationFn: () => api.delete(`/api/v1/accounts/${account.id}`, { confirm_nickname: confirm }),
    onSuccess: () => {
      setDeleting(false);
      refresh();
    },
    onError: (err) => setError(errorMessage(err)),
  });

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          {account.nickname}
          {account.id === accountId && <Badge color="#22c55e">{t("admin.accounts.active")}</Badge>}
          {account.linked ? <Badge>{t("admin.accounts.linked")}</Badge> : <Badge color="#94a3b8">{t("admin.accounts.notLinked")}</Badge>}
        </span>
      }
      actions={
        account.id !== accountId && (
          <Button size="sm" onClick={() => setAccountId(account.id)}>
            {t("admin.accounts.use")}
          </Button>
        )
      }
    >
      <KeyValue
        items={[
          [t("admin.accounts.nameInGame"), account.source_nickname ?? t("admin.accounts.nameInGameUnknown")],
          [t("admin.accounts.pokemonCount"), num(account.pokemon_count)],
          [t("admin.accounts.lastSync"), dateTime(account.last_successful_sync_at)],
          [t("admin.accounts.webhook"), account.webhook?.active ? t("admin.accounts.webhookActive", { date: dateTime(account.webhook.created_at) }) : t("admin.accounts.webhookNone")],
        ]}
      />
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Field label={t("admin.accounts.nameInOak")}>
          <Input value={nickname} maxLength={64} onChange={(e) => setNickname(e.target.value)} />
        </Field>
        <Field label={t("admin.accounts.maxDropPercent")} hint={t("admin.accounts.maxDropPercentHint")}>
          <Input type="number" min={1} max={100} value={fraction} onChange={(e) => setFraction(Number(e.target.value))} />
        </Field>
        <Field label={t("admin.accounts.maxDropCount")} hint={t("admin.accounts.maxDropCountHint")}>
          <Input type="number" min={0} value={absolute} onChange={(e) => setAbsolute(Number(e.target.value))} />
        </Field>
      </div>
      {error && (
        <div className="mt-3">
          <Alert tone="error">{error}</Alert>
        </div>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>
          {t("admin.accounts.save")}
        </Button>
        <Link to="/admin/sync">
          <Button>{t("admin.accounts.linkPgsharp")}</Button>
        </Link>
        {account.linked && (
          <Button
            onClick={() => {
              if (window.confirm(t("admin.accounts.unlinkConfirm"))) unlink.mutate();
            }}
          >
            {t("admin.accounts.unlink")}
          </Button>
        )}
        <Button variant="danger" onClick={() => setDeleting(true)}>
          {t("admin.accounts.delete")}
        </Button>
      </div>
      <Dialog
        open={deleting}
        onClose={() => setDeleting(false)}
        title={t("admin.accounts.deleteTitle", { name: account.nickname })}
        footer={
          <>
            <Button onClick={() => setDeleting(false)}>{t("common.cancel")}</Button>
            <Button variant="danger" disabled={confirm !== account.nickname} loading={remove.isPending} onClick={() => remove.mutate()}>
              {t("admin.accounts.deleteSubmit")}
            </Button>
          </>
        }
      >
        <p className="text-sm">
          {/* The nickname is user input: escaped for the markup parser, then shown as plain text again. */}
          <Trans
            i18nKey="admin.accounts.deleteText"
            values={{ name: account.nickname }}
            components={{ b: <b /> }}
            tOptions={{ interpolation: { escapeValue: true } }}
            shouldUnescape
          />
        </p>
        <Input className="mt-3" value={confirm} onChange={(e) => setConfirm(e.target.value)} aria-label={t("admin.accounts.deleteConfirmName")} />
      </Dialog>
    </Card>
  );
}

export function AccountsPage() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const { accounts, loading, setAccountId } = useAccount();
  const [nickname, setNickname] = useState("");
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => api.post<Account>("/api/v1/accounts", { nickname }),
    onSuccess: (account) => {
      setNickname("");
      setError(null);
      setAccountId(account.id);
      void client.invalidateQueries({ queryKey: ["accounts"] });
    },
    onError: (err) => setError(errorMessage(err)),
  });
  return (
    <>
      <PageHeader title={t("admin.accounts.title")} description={t("admin.accounts.description")} />
      <Card title={t("admin.accounts.newTitle")} className="mb-5">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (nickname.trim()) create.mutate();
          }}
        >
          <Field label={t("admin.accounts.name")}>
            <Input value={nickname} maxLength={64} onChange={(e) => setNickname(e.target.value)} placeholder={t("admin.accounts.namePlaceholder")} className="w-64" />
          </Field>
          <Button type="submit" variant="primary" loading={create.isPending} disabled={!nickname.trim()}>
            {t("admin.accounts.create")}
          </Button>
        </form>
        {error && (
          <div className="mt-3">
            <Alert tone="error">{error}</Alert>
          </div>
        )}
      </Card>
      {!loading && accounts.length === 0 ? (
        <EmptyState title={t("admin.accounts.emptyTitle")}>{t("admin.accounts.emptyText")}</EmptyState>
      ) : (
        <div className="grid gap-5 xl:grid-cols-2">
          {accounts.map((a) => (
            <AccountCard key={a.id} account={a} />
          ))}
        </div>
      )}
    </>
  );
}
