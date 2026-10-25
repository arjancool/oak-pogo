# Back-up en herstel

Alles wat OAK bewaart, staat in de datamap (`/data` in de container):

| Pad | Inhoud |
|---|---|
| `oak.db` met `oak.db-wal` en `oak.db-shm` | De SQLite-database: gebruikers, traineraccounts, Pokémon, historie, jouw OAK-gegevens en analyses. |
| `.secret_key` | De automatisch gemaakte geheime sleutel, als `OAK_SECRET_KEY` niet is ingesteld. |
| `backups/` | Back-ups van de database. |
| `gamedata/` | De bewaarde Game Data-versies. Die kun je altijd opnieuw downloaden. |
| `imports/` | Ontvangen exports, tijdelijk bewaard voor diagnose. Die verdwijnen na `OAK_RAW_IMPORT_RETENTION_DAYS`. |

## Automatische back-ups

Voor iedere databasemigratie maakt OAK zelf een kopie in `backups/`, met de oude schemaversie in de naam. Een update kan dus altijd worden teruggedraaid.

## Handmatige back-up

In **Beheer → Back-ups** maak en download je als eigenaar een back-up. OAK gebruikt daarvoor de back-upfunctie van SQLite, zodat de kopie ook tijdens gebruik consistent is.

Vanaf de host kan het ook, terwijl OAK draait:

```bash
docker exec -u 1000:1000 oak python -c "import sqlite3; s = sqlite3.connect('/data/oak.db'); d = sqlite3.connect('/data/backups/oak-handmatig.db'); s.backup(d)"
```

Gebruik bij `-u` dezelfde waarden als `PUID` en `PGID`, anders wordt het bestand van root.

Een volledige back-up van de datamap met de container gestopt is het eenvoudigst:

```bash
docker compose stop oak
tar czf oak-data-$(date +%F).tar.gz -C /media/docker/oak data
docker compose start oak
```

Bewaar `.secret_key` mee. Zonder die sleutel blijven je gegevens leesbaar, maar moet iedereen opnieuw inloggen en herkent OAK een export niet meer als afkomstig van hetzelfde Pokémon GO-account. Je moet het traineraccount dan opnieuw koppelen.

## Herstellen

1. Stop de container: `docker compose stop oak`.
2. Verplaats de huidige database met haar twee hulpbestanden naar een veilige plek. Ze horen bij elkaar, dus nooit los:
   `mkdir voor-herstel && mv data/oak.db data/oak.db-wal data/oak.db-shm voor-herstel/` (de laatste twee kunnen ontbreken).
3. Kopieer de back-up naar `data/oak.db` en geef hem dezelfde eigenaar: `chown 1000:1000 data/oak.db`.
4. Start de container: `docker compose start oak`.

Een back-up uit **Beheer → Back-ups** bevat alleen de database, niet de bestanden in `gamedata/`. Ontbreekt na het terugzetten het bestand van de actieve Game Data-versie, dan bouwt OAK het opnieuw op uit de bronnen, ook als die niet zijn veranderd. Met automatische updates aan gebeurt dat binnen een uur na het starten. Anders start je het zelf met **Beheer → Game Data → Nu bijwerken**.

Is de back-up van een oudere versie, dan migreert OAK hem bij het starten naar het huidige schema. Daarvoor maakt OAK eerst weer een back-up. Na het starten herberekent OAK analyses die met een oudere engineversie zijn gemaakt.

Een back-up van een nieuwere OAK-versie terugzetten in een oudere versie werkt niet. Gebruik dan de image van die nieuwere versie.

## Gegevens van één traineraccount

**Beheer → Traineraccounts** verwijdert alle OAK-gegevens van één account. In het spel verandert daardoor niets. Een kopie van alleen je eigen OAK-gegevens (bescherming, notities, tags en plannen) haal je op via de API: `GET /api/v1/export/metadata?account_id=<id>`. Een knop daarvoor in de interface ontbreekt nog.
