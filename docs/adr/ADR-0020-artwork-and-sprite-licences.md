# ADR-0020: Geen meegeleverde Pokémon-artwork, met gecontroleerde licentiegegevens

- Status: Accepted
- Date: 2026-10-23

## Context

OAK toont Pokémon. De afbeeldingen daarvan zijn het werk van de rechthebbenden (Nintendo, The Pokémon Company, Game Freak en Creatures). Een veelgebruikte bron is de repository `PokeAPI/sprites`. Die is op 23 oktober 2026 op de branch `master` gecontroleerd.

- Het `package.json` noemt de licentie ISC.
- Er is geen licentiebestand. `LICENSE`, `LICENSE.md`, `LICENSE.txt` en `COPYING` bestaan niet.
- De README noemt geen CC0 en geen auteursrecht van The Pokémon Company.
- De README vermeldt dat de sprites vanaf Pokémon: Let's Go Pikachu en Let's Go Eevee zijn gerenderd uit originele game-assets.

De licentie van de afbeeldingen is daarmee onduidelijk. Of het ISC-veld in `package.json` ook voor de afbeeldingen bedoeld is, staat nergens. Een licentie in een repository van derden kan het recht van de rechthebbenden niet veranderen.

## Besluit

De regels zijn:

- OAK bevat geen Pokémon-afbeeldingen in de broncode, de Docker-image, de testdata, de documentatie of de screenshots.
- Standaard toont OAK een eigen, gegenereerde badge met het Pokédex-nummer in de kleur van het type.
- Een externe spritebron staat standaard uit (`OAK_SPRITE_URL_TEMPLATE` is leeg). Alleen de eigenaar kan hem aanzetten, in de instellingen.
- De PokeAPI-sprites blijven beschikbaar als vooraf ingevulde keuze. Een eigen bron moet met `https://` beginnen en `{dex}` bevatten.
- Staat een spritebron aan, dan laadt de browser de afbeeldingen rechtstreeks bij die bron. OAK slaat ze niet op, stuurt ze niet door en verspreidt ze niet.
- De Content-Security-Policy staat voor afbeeldingen naast OAK zelf alleen de host van de ingestelde spritebron toe.
- OAK noemt een spritebron nooit vrij te gebruiken en schrijft er geen licentie aan toe. Het instellingenscherm meldt dat de afbeeldingen auteursrechtelijk beschermd zijn en dat het aanzetten een keuze van de eigenaar is.
- Licentiegegevens van bronnen staan in `docs/DATA_SOURCES.md`, met de datum waarop ze zijn gecontroleerd. Wie de vooraf ingevulde spritebron verandert, controleert de licentie opnieuw en werkt dat document bij.

## Gevolgen

- Standaard laadt OAK geen afbeeldingen van buiten.
- Wie OAK met een spritebron gebruikt, doet dat op eigen verantwoordelijkheid. Dat staat in `docs/DATA_SOURCES.md` en in het instellingenscherm.
