# ADR-0028: Game Data uit de Game Master van alexelgt en uit PvPoke, met versiebeheer

- Status: Accepted
- Date: 2026-11-06
- Vervangt: ADR-0017

## Context

ADR-0017 koos de Game Master van PokeMiners (`latest/latest.json`) als primaire bron. Die is sinds 28 augustus 2026 niet meer bijgewerkt. Op 6 november 2026 ontbraken daardoor nieuwe vormen, zoals Charmander, Charmeleon en Charizard met de bril van 2026. OAK rekende voor zulke Pokémon met de standaardvorm.

De repository [alexelgt/game_masters](https://github.com/alexelgt/game_masters) publiceert de Game Master van het spel in hetzelfde formaat, als `GAME_MASTER.json`, en wordt bijgehouden. Ook het project pokemon-go-api gebruikt die bron. Net als PokeMiners vermeldt de repository geen licentie, alleen een disclaimer dat de gegevens van The Pokémon Company en Niantic zijn.

In de nieuwere Game Master noemt Niantic een paar vormen alleen met een nummer, zoals `3362`, in plaats van een naam. OAK liep daarop vast. Dat is opgelost voordat de bron wisselde.

## Besluit

- De standaardbron voor de Game Master is `https://raw.githubusercontent.com/alexelgt/game_masters/master/GAME_MASTER.json`. Daaruit komen soorten, vormen, basisstatistieken, aanvallen voor PvE en PvP, evoluties en kosten, CP-multipliers, power-upkosten, het typeschema en de kosten van Max Moves.
- De bron blijft in te stellen met `OAK_GAMEDATA_POKEMINERS_URL`, ook terug naar PokeMiners. De naam van die instelling blijft gelijk, zodat bestaande installaties blijven werken.
- De datum van de gegevens komt uit `timestamp.txt` naast het bestand, zoals PokeMiners dat publiceert. Ontbreekt dat bestand en staat de Game Master op GitHub, dan geldt de datum van de laatste commit die het bestand veranderde, via de GitHub API. Anders is de datum onbekend, met de reden.
- PvPoke (MIT-licentie) blijft de aanvullende bron voor legacy-aanvallen, weergavenamen, league-rankings en cups (ADR-0027).
- OAK downloadt de bronnen tijdens gebruik, zet ze om naar een eigen genormaliseerd formaat, valideert dat en activeert het pas daarna. De vorige werkende versie blijft beschikbaar voor rollback.
- De Docker-image bevat geen Game Master-gegevens. Zonder netwerk kan een beheerder bestanden handmatig uploaden: `GAME_MASTER.json` of `latest.json`.
- Spelmechanica zoals de maximale level, CP-multipliers en kostenfactoren komen uit de actieve dataset, niet uit constanten in de code.

## Gevolgen

- Analyses vermelden de datasetversie waarop ze berekend zijn.
- Zonder actieve dataset tonen PvP- en cleanupmodules expliciet dat gegevens ontbreken in plaats van te gokken.
- Na de update haalt OAK bij de eerstvolgende controle de Game Master van alexelgt op. De bron is anders, dus OAK bouwt een nieuwe versie, ook als de vorige van PokeMiners kwam.
- Voor de datum vraagt OAK de GitHub API om de laatste commit van één bestand. Dat gebeurt alleen bij een update of een controle, en zonder inloggegevens.
- ADR-0022 en ADR-0027 verwijzen naar ADR-0017. Die verwijzingen gelden nu voor dit besluit.
