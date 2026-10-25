# Roadmap

Dit overzicht volgt de fasen uit de oorspronkelijke opdracht. Het zegt wat er in OAK 2.0 zit, wat gedeeltelijk klaar is en wat nog moet gebeuren. Open punten staan onderaan, op volgorde van belang.

## Fase 0: repository en ontwerp

Klaar. De besluiten staan in `docs/DECISIONS.md` en in de ADR's in `docs/adr/`. Architectuur, datamodel, PGSharp-koppeling, databronnen en analyse zijn beschreven in `docs/`.

## Fase 1: werkende Docker-basis

Klaar:

- Backend, frontend, SQLite en migraties.
- Eigenaaraccount, gebruikers en traineraccounts.
- Webhook en handmatige import met één gedeelde verwerking.
- Normalisatie met verliesvrije ID's en synchronisatiehistorie.
- Pokémon Box, detailpagina en dashboard.
- Docker-image, compose-bestand, CI en release.

## Fase 2: collectiebeheer en Cleanup

Klaar:

- Filters, zoeksyntax en dubbelen.
- Harde en zachte bescherming, met de bruikbaarheids- en bewaarscore (ADR-0019).
- Review, bulkacties op OAK-gegevens en de actielijst met bevestiging per Pokémon.
- CSV-export, een printbare checklist en zoekteksten voor in het spel.
- Historie per synchronisatie.
- Komende events uit de kalender van LeekDuck.com in het cleanupadvies (ADR-0021).

## Fase 3: PvP en evoluties

Klaar:

- Game Data met versiebeheer.
- CP- en levelberekening.
- Great, Ultra en Master League met IV-rang, soortrang en inzetbaarheid.
- Movesetadvies met Elite TM- en legacy-aanvallen.
- Evolutie- en power-upplanner, Team Builder met drie varianten.
- Rekenen met een Shadow Pokémon na purify (ADR-0022).

Gedeeltelijk: het resourcebudget. Stardust komt uit de export, maar candy per soort moet je zelf invoeren, omdat PGSharp die niet exporteert.

## Fase 4: PvE en Max Battles

Klaar:

- Raidcounters tegen een gekozen baas en de raidpositie per type.
- Team GO Rocket-counters.
- Herkenning van Dynamax met een overzicht van Max Moves en upgradekosten.

Gedeeltelijk:

- Gigantamax-herkenning is gebouwd, maar de waarde in de export is nog niet geverifieerd.
- Het raidmodel kijkt alleen naar schade per seconde, niet naar overleving.

## Fase 5: verfijning en beheer

Klaar:

- Back-ups vanuit de interface en vóór iedere migratie.
- Beveiligingstests voor sessies, CSRF, throttling en scheiding tussen gebruikers.
- Documentatie.
- Release naar ghcr.io voor amd64 en arm64.

Nog niet gebouwd: meldingen, extra statistieken en de optionele AI-coach (ADR-0009).

## Open punten

1. **De webhook verifiëren met een echte PGSharp-verzending.** Zet de diagnosemodus aan, ontvang één export en leg vast welk formaat PGSharp gebruikt. Werk daarna `docs/PGSHARP_INTEGRATION.md` bij.
2. **De arm64-image draaien.** De release publiceert de image voor amd64 en arm64 op ghcr.io, maar de arm64-versie heeft nog nergens gedraaid.
3. **Secret scanning en Dependabot-meldingen aanzetten** in de repository-instellingen. Dependabot-updates en een kwetsbaarheidsscan in CI zijn al ingericht.
4. **Gigantamax verifiëren** met een export waarin een Gigantamax-Pokémon zit.
5. **Een knop voor de export van OAK-gegevens.** De API bestaat al (`GET /api/v1/export/metadata`).
6. **Sprites per vorm.** De spritebron kent nu alleen het Pokédex-nummer en shiny, niet de vorm of het kostuum.
7. **Zoeken op evolueerbaar** in de Pokémon Box. Die zoekterm geeft nu een foutmelding, omdat de database niet weet welke evoluties mogelijk zijn.
8. **Het raidmodel uitbreiden** met overleving, zodat kwetsbare aanvallers niet te gunstig uitkomen.
9. **Tweestapsverificatie of OpenID Connect** voor wie OAK met meer mensen deelt.
10. **Meldingen**, bijvoorbeeld bij een mislukte import of nieuwe Game Data.
11. **Een optionele, lokale AI-coach** die alleen adviseert en nooit zelf iets wijzigt.
