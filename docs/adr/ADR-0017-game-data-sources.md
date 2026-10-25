# ADR-0017: Game Data uit PokeMiners en PvPoke met versiebeheer

- Status: Accepted
- Date: 2026-10-23
- Besluit: DEC-003

## Context

PGSharp levert accountgegevens maar geen basisstatistieken, aanvallen, evoluties of kosten. Battle-advies vraagt actuele, versiebeheerde spelgegevens.

## Besluit

- Primaire bron is de Game Master van PokeMiners (`latest/latest.json`). Daaruit komen soorten, vormen, basisstatistieken, aanvallen voor PvE en PvP, evoluties en kosten, CP-multipliers, power-upkosten, typeschema en Max Move-kosten.
- Aanvullende bron is PvPoke (MIT-licentie). Daaruit komen legacy-aanvallen, weergavenamen en de league-rankings voor Great, Ultra en Master League.
- OAK downloadt beide bronnen tijdens gebruik, zet ze om naar een eigen genormaliseerd formaat, valideert dat en activeert het pas daarna. De vorige werkende versie blijft beschikbaar voor rollback.
- De Docker-image bevat geen Game Master-gegevens. Zonder netwerk kan een beheerder bestanden handmatig uploaden.
- Spelmechanica zoals de maximale level, CP-multipliers en kostenfactoren komen uit de actieve dataset, niet uit constanten in de code.

## Gevolgen

- Analyses vermelden de datasetversie waarop ze berekend zijn.
- Zonder actieve dataset tonen PvP- en cleanupmodules expliciet dat gegevens ontbreken in plaats van te gokken.
