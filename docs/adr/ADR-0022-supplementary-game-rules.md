# ADR-0022: Spelregels die niet in de Game Master staan

- Status: Accepted
- Date: 2026-10-25
- Besluit: DEC-007
- Vult aan: ADR-0017

## Context

Een gebruiker purifyde een Shadow Machop met IV's 4/13/5 op level 8 en liet hem daarna evolueren. In het spel werd dat een Machoke van 1355 CP en daarna een Machamp van 2066 CP. OAK voorspelde 418 en 639 CP, en raadde Machamp aan voor Great League.

OAK rekende goed voor een Shadow Pokémon die je zonder purify laat evolueren. Purify verandert de Pokémon echter. Hij gaat naar je trainerlevel, met een maximum van level 25, als hij daaronder zat, en iedere IV krijgt er 2 punten bij tot 15. Dat is niet terug te draaien, en een level kun je niet verlagen. De Machamp van 2066 CP kan daardoor nooit meer in Great League.

ADR-0017 zegt dat spelmechanica uit de actieve dataset komt en niet uit constanten in de code. De Game Master van PokeMiners bevat wel de kosten van purify en de aanval die Frustration vervangt, maar niet het level en de IV-bonus. PvPoke bevat ze ook niet. Dat is op 25 oktober 2026 gecontroleerd in beide bestanden.

## Besluit

- Spelregels die in geen van beide bronnen staan, levert OAK zelf aan in `backend/app/gamedata/supplement.py`. Iedere regel noemt zijn bron en de datum van controle.
- De omzetting neemt die regels op in iedere dataset, onder `mechanics`. De analyse leest ze dus uit de actieve dataset, net als de andere spelregels.
- Een wijziging in het supplement verhoogt de revisie van de omzetting. OAK bouwt de actieve dataset dan opnieuw op uit dezelfde bronnen.
- Ontbreekt een regel in de dataset, dan meldt de controle dat en toont OAK het betrokken onderdeel als onbekend. Er is geen stille terugval.
- De eerste regels zijn die voor purify: `min_level` 25, begrensd door het trainerlevel, en `iv_bonus` 2. Bron is Bulbapedia, *Shadow Pokémon (GO)*. De uitkomst is nagerekend met de Machop hierboven en klopt op de CP.
- De battle-analyse, de evoluties en de power-ups van een Shadow Pokémon zijn ook te bekijken zoals hij na purify zou zijn. Is purify de geplande actie, dan toont OAK die weergave eerst.

## Gevolgen

- Het supplement is een tweede bron naast de Game Master en PvPoke. Het moet klein blijven en alleen regels bevatten die nergens anders staan.
- Verandert Niantic de regels, dan moet het supplement worden bijgewerkt. Tot dan rekent OAK met de oude waarden, en de dataset noemt de datum van controle.
- Als het trainerlevel onbekend is, gaat OAK uit van trainerlevel 25 of hoger en zegt dat erbij.
- De Cleanup-engine beoordeelt een Pokémon zoals hij nu is. Het purify-scenario is een hulpmiddel voor de keuze, geen nieuwe status.
