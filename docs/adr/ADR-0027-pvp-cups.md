# ADR-0027: PvP-cups uit PvPoke

- Status: Accepted
- Date: 2026-10-26
- Vult aan: ADR-0017

## Context

OAK kende alleen Great, Ultra en Master League. In de GO Battle League lopen ook cups met eigen regels, zoals de Fantasy Cup: maximaal 1500 CP en alleen Pokémon van het type Staal, Draak of Fee. Welke Pokémon uit je collectie daar mee kunnen, kon OAK niet zeggen.

De Game Master van het spel bevat de regels van een cup pas als die cup loopt, en niet op een vaste plek. PvPoke houdt in zijn `gamemaster.json` bij welke formats het op zijn site toont (`formats`) en beschrijft per cup de regels met filters (`cups`). Voor de meeste cups publiceert PvPoke ook een ranglijst. Die lijst bevat alleen soorten die PvPoke sterk genoeg vindt, dus hij zegt niet volledig wie mee mag.

## Besluit

- De cups die OAK kent, zijn de formats die PvPoke toont, behalve PvPoke's vrije format *Custom*. Een cup krijgt het ID `<cup>-<CP-limiet>`, bijvoorbeeld `fantasy-1500`.
- Bij het bouwen van een Game Data-versie past OAK de filters van PvPoke toe zoals PvPoke dat zelf doet, en bewaart per cup de lijst met PvPoke-soorten die mee mogen. Twee keuzes van PvPoke neemt OAK niet over, omdat het geen spelregels zijn: de ondergrens voor het statproduct en de Little Cup-regel voor Shadow Pokémon onder level 8.
- Een cup met een filter dat OAK niet kent, biedt OAK niet aan. De Game Data-versie vermeldt waarom. Raden wie mee mag, zou een antwoord lijken zonder het te zijn.
- Een vorm zonder PvPoke-soort kan OAK niet toetsen. Die telt voor een cup als onbekend en komt niet in de lijst.
- OAK downloadt per cup de ranglijst van PvPoke. Ontbreekt die, dan blijft de cup bestaan en sorteert OAK je Pokémon alleen op IV-rang. De pagina zegt dat erbij.
- De analyse van een cup is dezelfde als die van een league: IV-rang, beste CP en level, inzetbaarheid, kosten en soortrang. Alleen doelen die de cup toelaat, tellen mee, en een levelgrens van de cup geldt ook. OAK slaat de uitkomst op naast die van de leagues.
- Cups tellen niet mee in het cleanupadvies. Een cup loopt een paar weken en mag niet bepalen wat je bewaart.

## Gevolgen

- De lijst met cups volgt PvPoke. Daar staan GO Battle League-cups tussen, maar ook toernooien uit de community. Of een cup nu in het spel loopt, weet OAK niet. De interface zegt dat.
- Een Game Data-update downloadt per cup een extra bestand van PvPoke, nu elf bestanden van 0,2 tot 1,2 MB.
- Met alle cups van PvPoke duurt de analyse van een collectie van 983 Pokémon ongeveer 2 seconden, met zo'n 17.000 regels in `pvp_rankings`.
- De kolom `league` in `pvp_rankings` en `battle_teams` is breder geworden (migratie `0006`), omdat een cup-ID langer kan zijn dan 16 tekens.
- Bij het controleren tegen de echte gegevens van PvPoke stond iedere soort uit de ranglijst van een cup ook in OAK's lijst van toegestane soorten.
