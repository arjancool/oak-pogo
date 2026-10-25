# ADR-0026: Gymverdedigers in het cleanupadvies

- Status: Accepted
- Date: 2026-10-25
- Vult aan: ADR-0019

## Context

ADR-0019 bepaalt dat de bruikbaarheidsscore de hoogste deelwaarde is van de league-rangen en de plaats tussen alle raid-aanvallers van een type. De waarde als gymverdediger telde niet mee. OAK berekende die alleen voor het overzicht *Gymverdedigers*.

Daardoor kon een goede verdediger die weinig waard is in PvP of raids een lage bruikbaarheid krijgen. Bij twee exemplaren van dezelfde soort koos OAK het beste op bruikbaarheid en IV-percentage, niet op Defense en HP. Het exemplaar dat het meeste kan incasseren, kon zo transfer-kandidaat worden.

Een Pokémon die in een gym staat, kun je in het spel niet overzetten. PGSharp vult dan per Pokémon het veld `deployedFortId`. Dat veld wijst naar een plaats, en het privacyfilter verwijderde het daarom.

## Besluit

- De bruikbaarheidsscore krijgt een gymwaarde als extra deelwaarde. De score blijft de hoogste deelwaarde, niet de som.
- De gymwaarde volgt uit de gympositie: waar dit exemplaar, of een vorm waarin het kan evolueren, zou staan tussen alle vormen die volgens de Game Data in een gym mogen (`isDeployable`). OAK vergelijkt Defense maal HP op het ingestelde maximale level met de eigen IV's. Het veld van vergelijking staat op het hoogste normale level met perfecte IV's. Andere vormen van dezelfde soort tellen niet mee.
- Plaats 1 telt volledig. De waarde loopt lineair af tot 0 na plaats `gym_top_n`, standaard 20. Zo krijgen alleen de beste verdedigerssoorten punten, net als bij raids.
- Een nieuwe regel `keep_best_gym`, standaard aan, bewaart per soort waarin een top-verdediger kan evolueren het exemplaar met de meeste Defense en HP.
- Uit `deployedFortId` bewaart OAK alleen of een Pokémon nu in een gym staat. Het privacyfilter zet die ja of nee in de plaats van het veld. Het gym-ID en de plaats komen nooit op schijf.
- Een transfer-kandidaat die in een gym staat, wordt *Beoordelen*, met de reden erbij. Het overzicht van gymverdedigers en de Pokémon Box tonen het ook.
- De engineversie wordt `cleanup-2.2`, zodat OAK alle adviezen opnieuw berekent.

## Gevolgen

- Verdedigers zoals Blissey en Snorlax krijgen een hogere bruikbaarheid. Er komen minder transfer-kandidaten bij die soorten.
- In een export van 983 Pokémon stond geen enkele Pokémon in een gym. Of PGSharp `deployedFortId` vult zoals verwacht, is daardoor nog niet vastgesteld. Zonder gevuld veld blijft *staat in een gym* onbekend en verandert er niets.
- Het verlies van motivatie en de eigen aanvallen van een verdediger tellen nog steeds niet mee.
