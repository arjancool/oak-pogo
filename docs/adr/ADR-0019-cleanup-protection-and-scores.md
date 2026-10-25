# ADR-0019: Zachte bescherming voor favorieten, harde bescherming voor vintage, twee scores

- Status: Accepted
- Date: 2026-10-23

## Context

De eerste versie van de Cleanup-engine beschermde iedere favoriet en iedere Pokémon van vóór 2019 automatisch. In een echte export van 974 Pokémon waren 860 favorieten. Daardoor kreeg vrijwel de hele collectie `PROTECT` en vergeleek OAK die Pokémon niet meer met andere exemplaren. Het advies hielp dan niet meer bij het vinden van overbodige exemplaren.

De eigenaar wil dat OAK de beste exemplaren helpt bewaren en overbodige exemplaren herkent, zonder dat waardevolle oude Pokémon verloren gaan.

## Besluit

### Ieder Pokémon wordt geanalyseerd

Bescherming bepaalt alleen de uiteindelijke status. Iedere Pokémon krijgt league-rangen, een raidpositie, een bruikbaarheidsscore, een bewaarscore en een vergelijking met andere exemplaren van dezelfde soort, vorm en Shadow-status. Ook beschermde, favoriete en vintage Pokémon doen mee in rollen als "beste Great League-kandidaat".

### Favorieten zijn een zachte bescherming

- Favoriet zijn is geen harde beschermingsregel meer. De regel `protect_favorites` is vervallen.
- Een favoriet krijgt extra punten in de bewaarscore (`keep_points_favorite`, standaard 25 van 100, instelbaar).
- Favorietenstatus telt nooit mee in de bruikbaarheidsscore, de league-rangen of de raidanalyse.
- Een favoriet die anders transfer-kandidaat zou zijn, krijgt `REVIEW` met een waarschuwing en de naam van het betere exemplaar dat bewaard blijft.
- Een favoriet komt alleen op een transferactielijst na een bevestiging per Pokémon.

### Vintage Pokémon zijn hard beschermd

- Pokémon gevangen in 2016, 2017, 2018 of 2019 zijn vintage. Dit is een vaste regel in de code (`VINTAGE_FIRST_YEAR`, `VINTAGE_LAST_YEAR`), geen instelling. De regel `protect_before_year` is vervallen.
- Ze krijgen altijd `PROTECT` met de reden "Vintage Pokémon (2016–2019)" en een badge met het jaar.
- Ze komen nooit via een bulkactie op een transferlijst.
- Wie de bescherming van één vintage Pokémon opheft (een handmatige status `REVIEW` of `TRANSFER_CANDIDATE`), moet dat expliciet bevestigen. Daarna blijft een waarschuwing zichtbaar en vraagt de actielijst opnieuw om bevestiging.
- Een Pokémon zonder bruikbare vangstdatum (geen datum, of een datum vóór 2016) wordt nooit als nieuw behandeld. Hij kan `REVIEW` krijgen, nooit direct `TRANSFER_CANDIDATE`.

### Twee scores, los van de harde bescherming

- De **bruikbaarheidsscore** (0–100) volgt uit feiten: IV-rang voor de soort die de Pokémon kan worden, de PvPoke-soortrang, de beschikbaarheid van de beste aanvallen en de plaats tussen alle raid-aanvallers van een type. De score is de hoogste deelwaarde, niet de som, zodat dezelfde IV's niet in iedere league opnieuw meetellen.
- De **bewaarscore** (0–100) telt punten op: een instelbaar deel van de bruikbaarheid, beste of enige exemplaar, bijzondere kenmerken (met een maximum), favoriet, bijnaam en een eigen plan in OAK. Iedere eigenschap telt één keer. IV's tellen alleen via de bruikbaarheid.
- Harde bescherming staat los van beide scores. Een vintage Pokémon met bewaarscore 5 blijft beschermd.
- Zonder harde bescherming en zonder rol bepaalt de bewaarscore het advies: vanaf `keep_threshold` (70) `KEEP`, vanaf `review_threshold` (40) `REVIEW`, daaronder `TRANSFER_CANDIDATE`.
- Het beste exemplaar van iedere groep blijft altijd bewaard zolang `keep_min_per_species` minstens 1 is. Daardoor heeft iedere transfer-kandidaat een beter of gelijkwaardig exemplaar dat blijft.

## Gevolgen

- De engineversie wordt `cleanup-2.0`. Bij het starten herberekent OAK automatisch iedere analyse die met een oudere versie is gemaakt.
- Migratie `0002` voegt `battle_score`, `keep_score` en `scores` toe aan `cleanup_recommendations`. Handmatige bescherming, notities en andere OAK-metadata blijven ongewijzigd.
- Opgeslagen instellingen met `protect_favorites` of `protect_before_year` worden genegeerd.
- De overige harde regels (shiny, lucky, hundo, Legendary en andere) blijven standaard aan. Wie zo'n regel uitzet, laat het kenmerk alleen nog als punten in de bewaarscore meetellen.
- Uitwerking en formules staan in `docs/ANALYSIS_ENGINE.md`.
