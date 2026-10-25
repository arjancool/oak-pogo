import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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
          {account.id === accountId && <Badge color="#22c55e">actief</Badge>}
          {account.linked ? <Badge>gekoppeld</Badge> : <Badge color="#94a3b8">nog niet gekoppeld</Badge>}
        </span>
      }
      actions={
        account.id !== accountId && (
          <Button size="sm" onClick={() => setAccountId(account.id)}>
            Gebruik dit account
          </Button>
        )
      }
    >
      <KeyValue
        items={[
          ["Naam in Pokémon GO", account.source_nickname ?? "onbekend tot de eerste import"],
          ["Pokémon in inventaris", num(account.pokemon_count)],
          ["Laatste succesvolle sync", dateTime(account.last_successful_sync_at)],
          ["Webhook", account.webhook?.active ? `actief sinds ${dateTime(account.webhook.created_at)}` : "geen"],
        ]}
      />
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Field label="Naam in OAK">
          <Input value={nickname} maxLength={64} onChange={(e) => setNickname(e.target.value)} />
        </Field>
        <Field label="Maximale daling (%)" hint="Daalt het aantal Pokémon meer dan dit percentage, dan behandelt OAK de import als gedeeltelijk.">
          <Input type="number" min={1} max={100} value={fraction} onChange={(e) => setFraction(Number(e.target.value))} />
        </Field>
        <Field label="Maximale daling (aantal)" hint="Beide grenzen moeten overschreden worden.">
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
          Opslaan
        </Button>
        <Link to="/admin/sync">
          <Button>PGSharp koppelen</Button>
        </Link>
        {account.linked && (
          <Button
            onClick={() => {
              if (window.confirm("Koppeling met het Pokémon GO-account vergeten? Gebruik dit alleen als je bewust een ander account aan deze trainer wilt koppelen.")) unlink.mutate();
            }}
          >
            Koppeling vergeten
          </Button>
        )}
        <Button variant="danger" onClick={() => setDeleting(true)}>
          Verwijderen
        </Button>
      </div>
      <Dialog
        open={deleting}
        onClose={() => setDeleting(false)}
        title={`${account.nickname} verwijderen`}
        footer={
          <>
            <Button onClick={() => setDeleting(false)}>Annuleren</Button>
            <Button variant="danger" disabled={confirm !== account.nickname} loading={remove.isPending} onClick={() => remove.mutate()}>
              Definitief verwijderen
            </Button>
          </>
        }
      >
        <p className="text-sm">
          Alle OAK-gegevens van dit account verdwijnen: Pokémon, notities, tags, plannen, imports en historie. Je Pokémon GO-account zelf
          verandert niet. Typ <b>{account.nickname}</b> om te bevestigen.
        </p>
        <Input className="mt-3" value={confirm} onChange={(e) => setConfirm(e.target.value)} aria-label="Bevestig naam" />
      </Dialog>
    </Card>
  );
}

export function AccountsPage() {
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
      <PageHeader title="Traineraccounts" description="Ieder Pokémon GO-account krijgt een eigen traineraccount in OAK, met eigen webhook en gegevens." />
      <Card title="Nieuw traineraccount" className="mb-5">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (nickname.trim()) create.mutate();
          }}
        >
          <Field label="Naam">
            <Input value={nickname} maxLength={64} onChange={(e) => setNickname(e.target.value)} placeholder="Bijvoorbeeld Hoofdaccount" className="w-64" />
          </Field>
          <Button type="submit" variant="primary" loading={create.isPending} disabled={!nickname.trim()}>
            Aanmaken
          </Button>
        </form>
        {error && (
          <div className="mt-3">
            <Alert tone="error">{error}</Alert>
          </div>
        )}
      </Card>
      {!loading && accounts.length === 0 ? (
        <EmptyState title="Nog geen traineraccounts">Maak hierboven je eerste account aan.</EmptyState>
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
