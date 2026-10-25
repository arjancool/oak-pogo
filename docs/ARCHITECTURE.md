# Architectuur

OAK is één container met drie onderdelen: een FastAPI-backend, een React-frontend en een SQLite-database in `/data`. Er zijn geen andere services nodig. De besluiten daarachter staan in ADR-0012 tot en met ADR-0020.

```
PGSharp ──webhook──▶ ┌────────────────────────────── container ──────────────────────────────┐
                     │  FastAPI (uvicorn)                                                   │
browser ──https────▶ │   ├─ /api/v1/…   REST-API, sessies, CSRF                              │
                     │   ├─ /health/…   live en ready                                        │
                     │   └─ /…          gebouwde React-app                                   │
                     │  Achtergrondverwerker (thread) met duurzame wachtrij in SQLite        │
                     │  SQLite  /data/oak.db   ·   Game Data  /data/gamedata                 │
                     └──────────────────────────────────────────────────────────────────────┘
                                         ▲
             PokeMiners en PvPoke ───────┘  (Game Data, alleen ophalen)
```

## Uitgangspunten

- **PGSharp is de bron van de accountstatus** (ADR-0012). OAK leest exports, maar stuurt nooit iets naar het spel en vraagt nooit om inloggegevens.
- **SQLite is de enige bron van waarheid** (ADR-0014). Iedere schemawijziging is een Alembic-migratie. Voor iedere migratie maakt OAK een back-up.
- **Huidige stand plus wijzigingshistorie** (ADR-0015). Iedere Pokémon heeft één rij met de actuele stand. Iedere wijziging bij een synchronisatie komt als onveranderbare gebeurtenis in `pokemon_change_events`. Een trigger in de database weigert wijzigingen aan die gebeurtenissen.
- **Afgeleide gegevens zijn projecties.** Soortnamen, levels, PvP-rangen en cleanup-adviezen kunnen altijd opnieuw berekend worden uit de export, de Game Data en de regels.
- **Gebruikers bezitten traineraccounts** (ADR-0016). Iedere query op accountgegevens filtert op traineraccount en gebruiker. Een object van een ander account geeft 404, niet 403.
- **Game Data heeft versiebeheer** (ADR-0017). Een nieuwe dataset wordt eerst gecontroleerd en pas daarna actief. De vorige versies blijven bewaard om terug te kunnen.
- **Geen meegeleverde artwork** (ADR-0020) en **geen afhankelijkheid van Hermes** (ADR-0010).

## Backend

De backend volgt een hexagonale indeling. Domeinlogica is pure Python en kent geen database, webframework of netwerk. `tests/test_architecture.py` bewaakt dat.

| Map | Inhoud |
|---|---|
| `app/domain` | Genormaliseerde Pokémon, importclassificatie, wijzigingsdetectie, de zoeksyntax en de vintage-regel. Puur. |
| `app/normalizers` | Van PGSharp-export naar het domeinmodel, het opschonen van opgeslagen exports en de structuursamenvatting voor diagnose. Puur. |
| `app/analysis` | Statistieken, CP en HP, PvP-rangtabellen, power-upkosten, evoluties, aanvallen en het raidmodel. Puur. |
| `app/recommendations` | Cleanup-regels, de twee scores en de Cleanup-engine. Puur. |
| `app/gamedata` | Downloaden, omzetten en valideren van Game Data, en het versiebeheer. |
| `app/ingestion` | Ontvangen en decoderen van exports, importjobs, synchronisatie en afgeleide kolommen. |
| `app/services` | Analyse per account, weergave van Pokémon, battle-overzichten, instellingen en de transferregels. |
| `app/repositories` | Box-filters en zoektermen vertaald naar SQL. |
| `app/models` | SQLAlchemy 2-modellen. Zie `docs/DATA_MODEL.md`. |
| `app/api` | FastAPI-routes onder `/api/v1`, afhankelijkheden voor sessie, CSRF en eigendom. |
| `app/auth` | Wachtwoorden (Argon2id), sessies en tokens. |
| `app/jobs` | Achtergrondverwerker en taken. |
| `app/core` | Configuratie, database, logging, middleware, foutafhandeling, rate limiting en migraties. |
| `migrations` | Alembic-migraties. |

### Een export verwerken

1. **Ontvangst.** De webhook (`POST /api/v1/ingest/pgsharp/{token}`) en de upload (`POST /api/v1/imports/upload`) leveren hetzelfde soort verzoek af. De webhook controleert het token in constante tijd, de grootte en de rate limit.
2. **Decoderen.** OAK verwijdert compressie (gzip of deflate), haalt een bestand uit multipart, verwerkt de tekenset en een eventuele BOM, en parseert de JSON.
3. **Importjob.** OAK berekent een hash van de inhoud. Een export die al eerder binnenkwam, wordt herkend als dubbel. De export wordt opgeschoond (zonder locaties, namen van andere spelers of interne spelers-ID's), gecomprimeerd opgeslagen en in de wachtrij gezet. Het verzoek krijgt direct antwoord (202).
4. **Normaliseren.** In de achtergrond zet OAK de export om naar het domeinmodel. Een onleesbaar veld wordt `None` met een melding. OAK gokt nooit een waarde.
5. **Classificeren.** OAK bepaalt of de import volledig, gedeeltelijk, ongeldig of verouderd is. Alleen een volledige import mag Pokémon als "niet meer in inventaris" markeren.
6. **Synchroniseren.** OAK vergelijkt per Pokémon op `trainer_account_id` plus `source_pokemon_id`, werkt de stand bij en legt gebeurtenissen vast: verschenen, gewijzigd, verdwenen of teruggekeerd. Items en trainerstatistieken gaan mee.
7. **Afleiden en analyseren.** Met de actieve Game Data berekent OAK soort, vorm, level, typen en aanvallen. Daarna draait de analyse: PvP-rangen, raidpositie, scores en cleanup-advies.

Upload en webhook gebruiken vanaf stap 2 precies dezelfde code.

### Achtergrondverwerking

De verwerker is een thread in hetzelfde proces. De wachtrij staat in de tabel `background_jobs`, zodat werk een herstart overleeft: bij het starten zet OAK onderbroken taken terug in de wachtrij. Taken zijn imports, analyses, Game Data-updates en het opnieuw afleiden na een Game Data-wissel. Ieder uur draait onderhoud: opgeslagen exports opruimen na de bewaartermijn en zo nodig op nieuwe Game Data controleren.

### Database

SQLite draait in WAL-modus met foreign keys aan en een busy timeout van 30 seconden. Schrijvende transacties beginnen met `BEGIN IMMEDIATE`, zodat twee schrijvers elkaar niet halverwege blokkeren. Lezen gebeurt in een gewone transactie. Een verzoek dat iets wijzigt (POST, PUT, PATCH, DELETE) krijgt een schrijvende sessie.

### API

De API is REST met JSON onder `/api/v1`. De OpenAPI-beschrijving op `/api/openapi.json` en de interactieve documentatie op `/api/docs` zijn alleen beschikbaar buiten productie (`OAK_ENV=development`). Grote identificaties zoals Pokémon-ID's en tag-ID's zijn altijd tekst.

Fouten hebben één vorm:

```json
{"error": {"code": "NOT_FOUND", "message": "Pokémon niet gevonden.", "details": null}}
```

## Frontend

React 19 met TypeScript in strict mode, gebouwd met Vite. Data komt via TanStack Query, tabellen via TanStack Table, opmaak via Tailwind. Alle teksten zijn Nederlands.

| Map | Inhoud |
|---|---|
| `src/pages` | Pagina's per onderdeel: dashboard, Pokémon, cleanup, battles, account en beheer. |
| `src/components` | Gedeelde bouwstenen (`ui`), Pokémon-weergave, de opmaak met zijbalk en de bevestigingsdialoog voor transferlijsten. |
| `src/lib` | API-client, Zod-schema's, opmaak van getallen en datums, vertalingen, sessie en actief account. |

Zod-schema's controleren ieder antwoord met ID's. Een numeriek Pokémon-ID wordt geweigerd, omdat JavaScript zo'n getal niet exact kan bewaren. Filters in de Pokémon Box staan in de URL, zodat een gefilterde weergave te bewaren en te delen is.

## Tests en kwaliteit

- Backend: ruff, pyright en pytest. Tests draaien tegen een echte SQLite-database in een tijdelijke map, met een kleine Game Data-testset (`fixtures/gamedata`) en een synthetische export (`fixtures/pgsharp`).
- Frontend: ESLint, TypeScript en Vitest met Testing Library.
- End-to-end: Playwright tegen een echte server met de gebouwde frontend.
- CI draait dit alles bij iedere push, en bouwt en start daarnaast de Docker-image.

## Bewuste grenzen

- Eén proces en één database. OAK is bedoeld voor een huishouden of een kleine groep, niet voor duizenden gelijktijdige gebruikers.
- De Game Data komt van externe bronnen die niet officieel zijn. Zie `docs/DATA_SOURCES.md`.
- AI-functies zijn optioneel en nog niet gebouwd. Kernfunctionaliteit hangt nooit van een AI-dienst af.
