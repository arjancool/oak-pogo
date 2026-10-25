# Bijdragen aan OAK

OAK werkt met korte branches, kleine pull requests, squash-merges en [Conventional Commits](https://www.conventionalcommits.org/). Lees eerst `CLAUDE.md`, `AGENTS.md`, `docs/ARCHITECTURE.md` en de ADR's in `docs/adr/`. Een architectuurwijziging krijgt een nieuwe ADR. Een geaccepteerde ADR verandert alleen via een nieuwe ADR die hem vervangt.

## Ontwikkelomgeving

Je hebt Python 3.13 en Node 22 nodig.

### Backend

```bash
cd backend
python3.13 -m pip install --require-hashes -r build-requirements.txt   # uv, vastgezet met controlesommen
uv sync --locked --extra dev
OAK_ENV=development OAK_DATA_DIR=.oak-dev OAK_GAMEDATA_AUTO_UPDATE=false .venv/bin/python -m app
```

Op Windows werkt het hetzelfde. De programma's staan dan in `.venv\Scripts` in plaats van `.venv/bin`. CI start OAK ook op Windows.

De backend draait dan op <http://localhost:8080>. Met `OAK_ENV=development` staat de API-documentatie op <http://localhost:8080/api/docs>. Laat `OAK_GAMEDATA_AUTO_UPDATE` weg als je de echte Game Data wilt downloaden.

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

Vite draait op <http://localhost:5173> en stuurt `/api` en `/health` door naar de backend op poort 8080.

## Controles voor een commit

```bash
cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pyright && .venv/bin/pytest
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

De end-to-end test start zelf een server met de testset Game Data en de gebouwde frontend:

```bash
cd frontend && npm run build && npm run e2e
```

Playwright heeft eenmalig een browser nodig: `npx playwright install chromium`.

`backend/tests/test_real_export.py` controleert de cleanup-regels op een echte export. Hij draait alleen met `OAK_TEST_REAL_EXPORT=/pad/naar/PGSStats.json` en heeft internet nodig. Een echte export is persoonlijke data: zet hem nooit in de repository.

## Regels

- Iedere Python-afhankelijkheid staat met controlesom in `backend/uv.lock`. Wijzig je `pyproject.toml`, werk de lock dan bij met `uv lock` en commit beide. CI faalt als ze niet bij elkaar passen.
- Iedere schemawijziging krijgt een Alembic-migratie: `cd backend && .venv/bin/alembic revision --autogenerate -m "korte omschrijving"`. Controleer de gegenereerde migratie altijd met de hand.
- Domeinlogica in `app/domain`, `app/analysis`, `app/recommendations` en `app/normalizers` importeert geen database, webframework of netwerk.
- Pokémon-ID's en tag-ID's zijn overal tekst. Gebruik in de frontend nooit een `Number` voor zo'n ID.
- Nieuwe functionaliteit krijgt tests. Gedrag dat verandert, krijgt bijgewerkte documentatie.
- Geen geheimen, echte exports of Pokémon-artwork in de repository.

## Licentie

Door bij te dragen ga je ermee akkoord dat je bijdrage onder de Apache License 2.0 valt.
