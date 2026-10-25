# ADR-0014: SQLite en één container

- Status: Accepted
- Date: 2026-10-23

## Context

OAK richt zich op een particuliere installatie met een paar gebruikers en enkele duizenden Pokémon per account, en moet in één container draaien zonder externe services.

## Besluit

- SQLite in `/data/oak.db` is de enige bron van waarheid.
- Verbindingen gebruiken `foreign_keys=ON`, WAL-modus, `busy_timeout` en `synchronous=NORMAL`.
- Schrijvende importtransacties starten met `BEGIN IMMEDIATE`, zodat er nooit twee schrijvers tegelijk een import verwerken.
- Achtergrondtaken lopen in het applicatieproces via een duurzame takentabel. Er is geen aparte wachtrijdienst nodig.
- Datatoegang verloopt via repositories met SQLAlchemy 2. Er zit geen SQLite-specifieke SQL in services of domeinlogica, zodat een latere overstap naar PostgreSQL alleen de adapterlaag raakt.
- 64-bitsidentificaties boven `2^63 - 1` passen niet in een SQLite-INTEGER en worden als `TEXT` opgeslagen.

## Gevolgen

- De applicatie draait met één Uvicorn-worker. Horizontale schaal valt buiten scope.
- Back-ups gebruiken de SQLite online backup-API, zodat een kopie consistent is terwijl OAK draait.

## Verworpen alternatieven

PostgreSQL met Redis is verworpen omdat dat minimaal drie containers vraagt en de opdracht dat uitsluit.
