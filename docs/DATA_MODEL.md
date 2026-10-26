# Datamodel

Alle gegevens staan in één SQLite-database, `/data/oak.db`. Het schema wordt beheerd met Alembic-migraties in `backend/migrations`. De modellen staan in `backend/app/models`.

Drie soorten gegevens worden strikt gescheiden:

- **Brongegevens** komen uit de PGSharp-export en worden bij iedere import bijgewerkt.
- **OAK-gegevens** zijn wat jij in OAK vastlegt: bescherming, notities, tags, plannen, actielijsten en tag-namen. Een import raakt die nooit.
- **Projecties** zijn afgeleid en kunnen altijd opnieuw worden berekend: soortnamen, levels, PvP-rangen, scores en cleanup-adviezen.

Grote identificaties (Pokémon-ID's, tag-ID's) zijn overal tekst, ook in de database, zodat geen cijfer verloren gaat.

## Gebruikers

| Tabel | Inhoud |
|---|---|
| `users` | Gebruikersnaam, Argon2id-hash van het wachtwoord, rol (`owner` of `user`), status en voorkeuren. |
| `user_sessions` | Sessies. Alleen de SHA-256-hash van het sessietoken wordt bewaard, met laatste gebruik, verloopmoment en intrekking. |
| `audit_log` | Beveiligingsrelevante handelingen, zoals inloggen, wachtwoordwijzigingen, webhooks, back-ups en het verwijderen van accounts. |

## Traineraccounts

| Tabel | Inhoud |
|---|---|
| `trainer_accounts` | Eén Pokémon GO-account van een gebruiker. Naam in OAK, naam in het spel, level, XP, Stardust, PokéCoins, team, opslag, trainerstatistieken, syncstatus en instellingen (volledigheidsgrenzen en cleanup-regels). `source_fingerprint` is de HMAC-vingerafdruk van het Pokémon GO-account. |
| `webhook_credentials` | Webhook-tokens: een openbaar deel om het record te vinden en de SHA-256-hash van het geheel. Status actief of ingetrokken. |
| `item_inventory` | De huidige item bag. |
| `inventory_snapshots` | Items en trainerstand per synchronisatie, voor de historie. |
| `manual_resources` | Candy en XL Candy die je zelf invoert, omdat PGSharp die per soort niet exporteert. |
| `tag_labels` | Namen voor in-game tags en of een tag beschermt. |

Alle tabellen onder een traineraccount verwijzen ernaar met `ON DELETE CASCADE`. Verwijder je een traineraccount, dan verdwijnen alle bijbehorende gegevens.

## Imports

| Tabel | Inhoud |
|---|---|
| `import_jobs` | Iedere ontvangen export: bron (webhook, upload of opnieuw), status, voortgang, hash en grootte, het pad van de opgeslagen export, verzoekgegevens, structuursamenvatting, vingerafdruk, exportmoment, classificatie en fouten. |
| `import_errors` | Meldingen per import, met ernst, code, de gegevens in de melding, pad en eventueel de Pokémon-ID. |
| `sync_runs` | Het resultaat van een verwerkte import: classificatie, aantallen nieuw, gewijzigd, ongewijzigd, verdwenen, niet bevestigd en teruggekeerd, en waarschuwingen. Iedere run verwijst naar de vorige. |
| `background_jobs` | De duurzame wachtrij van de achtergrondverwerker. |

## Pokémon

### `pokemon`

Eén rij per Pokémon per traineraccount. De identiteit is `trainer_account_id` plus `source_pokemon_id` (uniek). Twee Pokémon van dezelfde soort met dezelfde CP zijn dus nooit vanzelf hetzelfde exemplaar.

- **Brongegevens** uit de export: soort en vorm, kostuum, geslacht, shiny, Shadow of Purified, lucky, favoriet, CP en HP, IV's, CP-multiplier, aanvallen, power-ups, lengte en gewicht, vangstmoment, ruilmoment, herkomst, of de Pokémon nu in een gym staat (`in_gym`), achtergrond, Dynamax-stand en Max Moves, mega-voortgang, bijnaam, buddy- en gevechtsgegevens, tag-ID's en onbekende extra velden (`extra`).
- **Afgeleide kolommen** uit Game Data en tijdzone: IV-percentage, vangstjaar, level, soortnaam, vormsleutel, vormlabel, hoe de vorm is gevonden (`form_resolution`), typen, klasse (Legendary, Mythical of Ultra Beast), familie en de sleutels van de aanvallen. `derived_version_id` zegt met welke Game Data-versie ze berekend zijn. Na een Game Data-wissel berekent OAK ze opnieuw.
- **Inventarisstatus**: `in_inventory` of `not_in_inventory`, met de eerste en laatste synchronisatie waarin de Pokémon voorkwam en het moment van verdwijnen.

Een Pokémon die uit de inventaris verdwijnt, blijft als rij bestaan. Komt hij in een latere export terug, dan krijgt hij de status `in_inventory` weer.

### `pokemon_change_events`

De historie. Iedere synchronisatie schrijft per Pokémon een gebeurtenis als er iets veranderde: `APPEARED`, `CHANGED`, `DISAPPEARED` of `REAPPEARED`, met de gewijzigde velden (oud en nieuw). Een trigger weigert iedere wijziging aan bestaande gebeurtenissen.

### `pokemon_user_metadata`

Jouw gegevens per Pokémon: handmatige bescherming met reden, notities, OAK-tags, geplande actie en league, prioriteit, reviewstatus, een handmatig vastgestelde cleanup-status en het moment van de laatste review.

### `planned_actions`

Actielijsten, zoals de cleanup-actielijst. Per Pokémon één keer per lijst, met status `open` of `done`. `confirmed` bewaart de concrete redenen die de gebruiker voor die Pokémon bevestigde: `favorite`, `unknown_date`, `vintage`, `protected:<regelcode>` zoals `protected:SHINY`, en `protected:TAG:<tag-ID>`. OAK controleert de bescherming opnieuw bij lezen, exporteren en afronden, en houdt een Pokémon tegen zodra er een reden bijkomt die niet bevestigd is. Bevestigingen van vóór deze indeling bevatten alleen `protected`; voor regelbescherming vraagt OAK die opnieuw.

## Game Data

| Tabel | Inhoud |
|---|---|
| `game_data_versions` | Iedere Game Data-versie: status (`active`, `ready`, `archived`, `pruned` of `failed`), herkomst (download of upload), schemaversie, hash, bestandsnaam, bronnen met controlegetallen, samenvatting en fout. De dataset zelf staat gecomprimeerd in `/data/gamedata`. OAK bewaart de drie nieuwste bruikbare versies. |
| `app_settings` | Instellingen voor de hele installatie, zoals de spritebron en het moment van de laatste Game Data-controle. |

## Events

| Tabel | Inhoud |
|---|---|
| `game_events` | Events uit de kalender van LeekDuck.com (`source` is `leekduck`, zonder traineraccount) en events die een gebruiker zelf toevoegt (`source` is `manual`, met traineraccount). Per event de naam, soort, begin en einde in UTC, of de tijd lokaal was, de link, de uitgelichte Pokémon als namen of Pokédex-nummers, de bonusteksten en de versie van de kalender. |

Een nieuwe kalender vervangt alle `leekduck`-events in één transactie. Eigen events blijven staan. Welke kalenderevents een traineraccount negeert, staat in de instellingen van dat account onder `ignored_events`.

## Analyse

| Tabel | Inhoud |
|---|---|
| `analysis_runs` | Iedere analyse per traineraccount: engineversie, Game Data-versie, regels met hun hash, een vingerafdruk van de invoer en een samenvatting. Is de invoer veranderd, dan meldt de Cleanup Manager dat het advies verouderd is. |
| `cleanup_recommendations` | Per Pokémon het laatste advies: status, prioriteit, betrouwbaarheid, beschermingsredenen, redenen, rollen, vergelijkbare Pokémon, waarschuwingen, de beste league-rangen, de bruikbaarheidsscore, de bewaarscore en de opbouw van beide scores (`scores`). |
| `pvp_rankings` | Per Pokémon, league of cup en doelsoort: IV-rang, statproduct, percentage van de beste, beste CP en level, inzetbaarheid, kosten en de soortrang uit PvPoke. Een cup staat er onder zijn ID, zoals `fantasy-1500` (ADR-0027). |
| `battle_teams`, `battle_team_members` | Teams die je in de Team Builder bewaart. |

Een nieuwe analyse vervangt de vorige projectie van dat traineraccount in één transactie.

## Bestanden in `/data`

| Pad | Inhoud |
|---|---|
| `oak.db` | De database. |
| `.secret_key` | De automatisch gemaakte geheime sleutel, als `OAK_SECRET_KEY` niet is ingesteld. |
| `imports/` | Opgeschoonde, gecomprimeerde exports, tot de bewaartermijn verloopt. |
| `gamedata/` | Game Data-versies. |
| `backups/` | Back-ups van de database. |

## Migraties

| Revisie | Wijziging |
|---|---|
| `0001` | Het eerste schema van OAK 2.0. |
| `0002` | `battle_score`, `keep_score` en `scores` in `cleanup_recommendations` (ADR-0019). |
| `0003` | `confirmed` in `planned_actions`: de bevestigde beschermingen per Pokémon op een actielijst. |
| `0004` | `game_events`: de eventkalender en eigen events (ADR-0021). |
| `0005` | `in_gym` in `pokemon`: of een Pokémon nu in een gym staat (ADR-0026). |
| `0006` | De kolom `league` in `pvp_rankings` en `battle_teams` is 48 tekens breed, voor cup-ID's (ADR-0027). |
| `0007` | `data` in `import_errors`, `error_data` in `import_jobs` en `errors` in `game_data_versions`: de gegevens in een opgeslagen melding, zodat de interface hem in de gekozen taal toont (ADR-0025). |

OAK voert migraties zelf uit bij het starten en maakt daarvoor een back-up in `backups/`.
