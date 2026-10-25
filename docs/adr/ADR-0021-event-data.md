# ADR-0021: Eventgegevens van LeekDuck via ScrapedDuck, met regels in plaats van AI

- Status: Accepted
- Date: 2026-10-25

## Context

Het cleanupadvies houdt geen rekening met events die eraan komen. Een Pokémon kan transfer-kandidaat zijn terwijl over een week zijn Community Day begint, waarop evolueren een speciale aanval kan geven. Een transfer is niet terug te draaien, dus zo'n advies kan de gebruiker een Pokémon kosten.

De vraag was of een AI dit kan oplossen. Het tekort is informatie, niet rekenkracht: een taalmodel weet niet welke events gepland zijn en verzint datums. Met eventgegevens als invoer kunnen gewone regels hetzelfde doen, maar uitlegbaar, reproduceerbaar en testbaar. ADR-0009 zegt bovendien dat kernfunctionaliteit geen AI nodig heeft, en `AGENTS.md` houdt AI-uitvoer buiten de deterministische beslislogica.

Niantic publiceert geen machineleesbare eventkalender. LeekDuck.com houdt een kalender bij. Het project ScrapedDuck zet die met toestemming van LeekDuck om naar JSON en publiceert die op GitHub. Op 25 oktober 2026 is `https://raw.githubusercontent.com/bigfoott/ScrapedDuck/data/events.json` gecontroleerd. Het bestand bevatte 59 events tot augustus 2027. Bij een Community Day staan de uitgelichte Pokémon en de bonussen erin, bij een Spotlight Hour de Pokémon en de bonus. De gebruiksvoorwaarden in de README van ScrapedDuck zijn: geen betaalmuur, geen advertenties en een bronvermelding voor ScrapedDuck en LeekDuck.com. Volgens de wiki gelden de limieten van GitHub en ververst GitHub de bestanden hooguit eens per vijf minuten.

## Besluit

- OAK haalt de eventkalender op van ScrapedDuck (`OAK_EVENTS_URL`), standaard iedere 12 uur (`OAK_EVENTS_UPDATE_INTERVAL_HOURS`). Dat kan uit met `OAK_EVENTS_AUTO_UPDATE=false`. De eigenaar kan ook handmatig bijwerken.
- Een download wordt gecontroleerd voordat hij de opgeslagen events vervangt. Een mislukte of ongeldige download laat de vorige events staan en meldt de fout.
- OAK bewaart per event alleen wat de regels nodig hebben: naam, soort, begin, einde, link, uitgelichte Pokémon en bonusteksten. Afbeeldingen neemt OAK niet over (ADR-0020).
- Iedere download krijgt een versie: de SHA-256 van het bestand en het moment van ophalen. Een advies dat op een event rust, noemt het event, de datum, de bron en die versie.
- De regels zijn deterministisch en staan in de domeinlaag. Een transfer-kandidaat uit de evolutielijn van een Pokémon met een Community Day binnen de ingestelde termijn wordt *Bewaren tot na het event*. Een Spotlight Hour of event met dubbele Transfer Candy levert bij transfer-kandidaten een tip op om daarop te wachten. Een beslissing die de gebruiker zelf vastlegde, gaat altijd voor.
- Een hold verloopt vanzelf aan het einde van het event. OAK berekent het advies opnieuw zodra een event binnen de termijn komt of afloopt.
- Per traineraccount kan de gebruiker een event negeren en zelf events toevoegen. Die gelden alleen voor dat account (ADR-0016).
- Het gebruik van events is per account uit te zetten (`use_events`), net als de termijn (`event_hold_days`, standaard 14 dagen).
- De pagina met events en `docs/DATA_SOURCES.md` vermelden LeekDuck.com en ScrapedDuck als bron.
- Een AI-assistent hoort hier niet bij. Komt die er later, dan alleen lokaal en adviserend, volgens ADR-0009, met een eigen besluit.

## Gevolgen

- OAK maakt een extra uitgaande verbinding naar `raw.githubusercontent.com`. Er gaan geen gegevens van de gebruiker mee.
- De gegevens zijn niet officieel en kunnen fouten bevatten of later veranderen. De betrouwbaarheid van een advies dat op een event rust, is daarom hooguit gemiddeld, en de link naar het event staat erbij.
- Namen van uitgelichte Pokémon koppelt OAK via de Game Data aan een soort. Lukt dat niet, dan toont de eventpagina dat en levert dat event geen hold op. Er is geen stille terugval.
- De engineversie gaat omhoog, zodat bestaande analyses opnieuw worden berekend.
