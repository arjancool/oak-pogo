# Instructies voor Claude Code in OAK

OAK is een self-hosted, Docker-first Pokémon GO-collectiebeheerder. PGSharp levert de accountgegevens, OAK analyseert ze en geeft uitlegbaar advies. OAK voert zelf nooit gameplay-acties uit.

## Werkwijze

1. Lees `AGENTS.md`, `docs/ARCHITECTURE.md` en de geaccepteerde ADR's in `docs/adr/`.
2. Bepaal welke modules, API-contracten, migraties en tests een wijziging raakt.
3. Leg een aanname die niet uit de documentatie volgt vast in de pull request.
4. Werk op een kortlevende branch in kleine, logisch opgebouwde commits (Conventional Commits).
5. Voeg tests toe of pas ze aan. Nieuwe functionaliteit vereist relevante tests.
6. Werk documentatie bij wanneer gedrag, contracten of besluiten veranderen.

## Vaste uitgangspunten

- FastAPI (Python 3.13) en React met TypeScript zijn de primaire technologieën.
- SQLite in `/data` is de enige bron van waarheid (ADR-0014). Schemawijzigingen krijgen altijd een Alembic-migratie.
- Pokémon-ID's, tag-ID's en andere 64-bitsidentificaties blijven verliesvrij. Ze zijn strings in de database (`TEXT`), in de API en in de frontend. Gebruik nooit een JavaScript `Number` voor zo'n ID.
- PGSharp-data is leidend voor de accountstatus. OAK-metadata (bescherming, notities, tags, plannen) staat in eigen tabellen en gaat nooit verloren door een import.
- Een ontbrekende Pokémon is alleen verdwenen na een aantoonbaar volledige, geldige import van hetzelfde account. Noem dat `Niet meer in inventaris`, nooit `Transferred`.
- Game Master-gegevens hebben versiebeheer en bronvermelding (ADR-0017). Spelmechanica komt uit de actieve dataset, niet uit constanten in de code.
- Domeinlogica in `backend/app/domain`, `analysis`, `recommendations` en `normalizers` importeert geen FastAPI, SQLAlchemy of andere infrastructuur. `tests/test_architecture.py` bewaakt dat.
- Iedere aanbeveling bevat actie, redenen, betrouwbaarheid, databron en datasetversie.
- Iedere Pokémon wordt geanalyseerd en vergeleken, ook beschermde, favoriete en vintage Pokémon. Bescherming bepaalt alleen de status (ADR-0019).
- Favorieten zijn een zachte bescherming: extra punten in de bewaarscore, nooit direct `TRANSFER_CANDIDATE` en alleen na een bevestiging per Pokémon op een transferlijst.
- Vintage Pokémon (gevangen in 2016–2019) zijn hard beschermd. Een bulkactie zet ze nooit op een transferlijst. Opheffen kan alleen per Pokémon, met bevestiging. Een onbekende vangstdatum betekent nooit dat een Pokémon nieuw is.
- De bruikbaarheidsscore en de bewaarscore blijven gescheiden. Favorietenstatus en vangstjaar tellen nooit mee in de bruikbaarheid. Harde bescherming staat los van beide scores, en geen eigenschap telt twee keer mee.
- Iedere query op accountgegevens filtert op traineraccount en gebruiker (ADR-0016).
- De Docker-build moet altijd werken. `docker compose up -d --build` is het referentiescenario.

## Verboden

- Geen automatische gameplay, geen automatische transfers, geen automatische evoluties of power-ups.
- Geen favoriet, vintage Pokémon of Pokémon met onbekende vangstdatum op een transferlijst zonder bevestiging van de gebruiker voor die Pokémon.
- Geen fictieve analyses, hardcoded productiedata of resultaten die compleet lijken zonder berekening.
- Geen stille fallback. Als een waarde onbekend is, toont OAK `onbekend` en vermeldt waarom.
- Geen Pokémon GO-inloggegevens vragen of opslaan.
- Geen secrets in de repository, ook niet in voorbeeldbestanden.
- Geen webhook-tokens, sessietokens of request-bodies in logs.
- Geen meegeleverde Pokémon-artwork (ADR-0020).
- Geen afhankelijkheid van een betaalde AI-dienst voor kernfunctionaliteit. AI-uitvoer is altijd adviserend.
- Geen directe koppeling met Hermes (ADR-0010).
- Een geaccepteerde ADR wijzigt alleen via een nieuwe ADR die hem vervangt.

## Controles voor een commit

```bash
cd backend && ruff check . && ruff format --check . && pyright && pytest
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```
