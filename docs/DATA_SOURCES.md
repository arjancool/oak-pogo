# Databronnen en licenties

OAK gebruikt twee soorten gegevens: je eigen export uit PGSharp, en algemene spelgegevens (Game Data) voor namen, statistieken, aanvallen en rankings. Deze pagina beschrijft per bron het doel, de licentie, de betrouwbaarheid en wat er gebeurt als de bron niet bereikbaar is.

De licenties zijn op 23 oktober 2026 gecontroleerd in de repositories zelf.

## Overzicht

| Bron | Doel | Licentie | Gebruik door OAK |
|---|---|---|---|
| PGSharp *Export Account Data* | Jouw Pokémon, items en trainerstatistieken | Niet van toepassing: het zijn jouw eigen gegevens | Alleen wat je zelf aanlevert |
| Game Master van alexelgt | Basisstatistieken, vormen, aanvallen, evoluties, kosten en spelmechanica | Geen licentie vermeld | Wordt tijdens gebruik gedownload, niet meegeleverd |
| PvPoke gamemaster en rankings | Namen, legacy-aanvallen, league-rankings en aanbevolen movesets | MIT | Wordt tijdens gebruik gedownload, niet meegeleverd |
| PokéAPI-sprites | Afbeeldingen van Pokémon | Zie hieronder | Standaard uit. Alleen als de eigenaar het aanzet, en dan laadt de browser ze rechtstreeks |
| LeekDuck.com via ScrapedDuck | Komende events voor het cleanupadvies | Gebruiksvoorwaarden van ScrapedDuck, zie hieronder | Wordt tijdens gebruik gedownload, niet meegeleverd |
| Engelse spelteksten via PokeMiners `pogo_assets` | De officiële Engelse namen van items | Geen licentie vermeld | Alleen de itemnamen staan in de code, met de bron. Het tekstbestand zelf zit er niet in |

## PGSharp-export

- **Doel:** de toestand van je Pokémon GO-account.
- **Herkomst:** de functie *Export Account Data* van PGSharp, via de webhook of als bestand. Zie `docs/PGSHARP_INTEGRATION.md`.
- **Betrouwbaarheid:** de gegevens komen uit het spel zelf en zijn per veld exact. PGSharp documenteert het formaat niet, dus OAK controleert ieder veld en meldt afwijkingen.
- **Beperkingen:** de export bevat geen candy per soort en geen namen van in-game tags. Die vul je zelf aan in OAK.
- **Privacy:** OAK verwijdert locaties, namen van andere spelers en interne spelers-ID's bij ontvangst.

## Game Master

- **URL:** standaard <https://github.com/alexelgt/game_masters>, bestand `GAME_MASTER.json` (ADR-0028). Met `OAK_GAMEDATA_POKEMINERS_URL` kies je een andere bron, bijvoorbeeld weer die van PokeMiners: <https://github.com/PokeMiners/game_masters>, bestand `latest/latest.json`. Beide hebben hetzelfde formaat.
- **Waarom alexelgt:** de Game Master van PokeMiners is sinds 28 augustus 2026 niet bijgewerkt. Daardoor ontbraken nieuwe vormen, zoals Charmander, Charmeleon en Charizard met de bril van 2026. alexelgt wordt bijgehouden, en ook het project pokemon-go-api gebruikt die bron.
- **Doel:** de primaire bron voor spelmechanica: basisstatistieken, typen, vormen, evoluties met hun eisen, aanvallen met kracht, energie en duur voor PvP en PvE, CP-multipliers, power-upkosten, Shadow- en Purified-regels, mega-evoluties, Max Battles en league-regels.
- **Licentie:** beide repositories vermelden geen licentie. Het gaat om gegevens die uit het spel zijn gehaald. OAK neemt ze daarom niet op in de broncode of de Docker-image, maar downloadt ze tijdens gebruik naar de eigen installatie.
- **Versie:** iedere download krijgt een eigen Game Data-versie in OAK, met de SHA-256 van het bestand, de ETag en het moment van ophalen.
- **Datum:** OAK zoekt eerst `timestamp.txt` naast het bestand, met het moment van de Game Master in milliseconden sinds 1970. PokeMiners publiceert dat, alexelgt niet. Ontbreekt het en staat de Game Master op GitHub, dan geldt de datum van de laatste commit die het bestand veranderde. Die vraagt OAK op bij de GitHub API (`api.github.com`). OAK toont op **Beheer → Game Data** van wanneer de actieve Game Master is en van wanneer de nieuwste, met de naam van de bron. Is er geen datum, of is die niet bereikbaar of ongeldig, dan staat er `onbekend` met de reden. Een update gaat dan gewoon door. Een geüpload bestand heeft geen datum van de bron.
- **Vormen met een nummer:** de nieuwere Game Master noemt een paar vormen alleen met een nummer, zoals `3362`. OAK leest zo'n nummer als de naam van de vorm.
- **Revisie van de omzetting:** iedere dataset noemt de revisie van de omzetting waarmee OAK hem bouwde. Voegt een nieuwe OAK-versie gegevens toe, zoals de G-Max-aanvallen (revisie 2), welke Pokémon in een gym mogen (revisie 3), de regels voor purify (revisie 4) of de cups (revisie 5), dan bouwt OAK de actieve versie bij de eerstvolgende update opnieuw op uit dezelfde bronnen. Met automatische updates aan gebeurt dat binnen een uur na het starten.
- **Betrouwbaarheid:** de Game Master is de bron die het spel zelf gebruikt. Sommige velden zijn onvolledig of dubbelzinnig, bijvoorbeeld vormen zonder eigen statistieken. OAK valt dan zichtbaar terug op de standaardvorm en verlaagt de betrouwbaarheid van het advies.

## PvPoke

- **URL:** <https://github.com/pvpoke/pvpoke>, bestanden `src/data/gamemaster.json` en `src/data/rankings/all/overall/rankings-1500.json`, `-2500.json` en `-10000.json`. Per cup die PvPoke toont ook `src/data/rankings/<cup>/overall/rankings-<CP-limiet>.json`.
- **Doel:** leesbare namen, de lijst met legacy-aanvallen, de soortrang per league en per cup, de aanbevolen movesets en de regels van de cups (ADR-0027).
- **Licentie:** MIT, Copyright (c) 2019 pvpoke.
- **Datum:** `gamemaster.json` vermeldt zelf zijn datum in het veld `timestamp`. OAK toont die bij de actieve versie.
- **Betrouwbaarheid:** de rankings komen uit simulaties van PvPoke. Ze zeggen hoe sterk een soort is, niet hoe goed jouw exemplaar is. OAK houdt die twee gescheiden.

## Itemnamen

De Engelse namen van items komen uit de teksten van het spel zelf. De app van Pokémon GO heeft een bestand met de Engelse teksten, `i18n_english`. PokeMiners publiceert dat in de repository [`pogo_assets`](https://github.com/PokeMiners/pogo_assets), onder `Texts/Latest APK/JSON`. Een item heet daar `item_<naam>_name`, met de `itemName` uit de PGSharp-export in kleine letters met underscores: `KingsRock` is `item_kings_rock_name`. De namen zijn op 6 november 2026 overgenomen in `backend/app/services/item_names.py`.

Pokémon GO bestaat niet in het Nederlands. Nederlandse spelers zien in het spel dus de Engelse namen, en OAK gebruikt die ook in het Nederlands. Alleen voor een paar items heeft OAK een Nederlandse vertaling, zoals voor de broedmachines.

Een item dat niet in de spelteksten staat, houdt de naam uit de PGSharp-export, in losse woorden. OAK verzint geen naam. Dat geldt nu voor `IncubatorSpecial` en `SoftSfida`. *Sfida* is in de spelteksten de interne naam van Pokémon GO Plus.

## Aanvullende spelregels van OAK

Een paar spelregels staan niet in de Game Master en niet bij PvPoke. OAK levert die zelf aan in `backend/app/gamedata/supplement.py` en neemt ze op in iedere dataset (ADR-0022).

| Regel | Waarde | Bron | Gecontroleerd |
|---|---|---|---|
| Level na purify | Het trainerlevel, maximaal 25, als de Pokémon daaronder zat | Bulbapedia, *Shadow Pokémon (GO)*. Nagerekend met een gepurifyde Machop in het spel | 25 oktober 2026 |
| IV's na purify | Iedere IV 2 punten hoger, tot 15 | Bulbapedia, *Shadow Pokémon (GO)*. Nagerekend met dezelfde Machop | 25 oktober 2026 |

## Eventkalender

- **URL:** <https://raw.githubusercontent.com/bigfoott/ScrapedDuck/data/events.json>, aan te passen met `OAK_EVENTS_URL`.
- **Doel:** komende events, zodat het cleanupadvies een Pokémon kan bewaren tot na zijn Community Day (ADR-0021).
- **Herkomst:** [LeekDuck.com](https://leekduck.com/events/) houdt de kalender bij. [ScrapedDuck](https://github.com/bigfoott/ScrapedDuck) zet die met toestemming van LeekDuck om naar JSON.
- **Voorwaarden:** volgens de README van ScrapedDuck geen betaalmuur, geen advertenties en een bronvermelding voor ScrapedDuck en LeekDuck.com. De pagina **Komende events** vermeldt beide. Gecontroleerd op 25 oktober 2026.
- **Wat OAK bewaart:** per event de naam, de soort, het begin, het einde, de link, de uitgelichte Pokémon en de bonusteksten. Afbeeldingen neemt OAK niet over.
- **Versie:** iedere download krijgt de SHA-256 van het bestand en het moment van ophalen. Een advies dat op een event rust, noemt die versie.
- **Tijden:** een tijd zonder `Z` is lokale tijd, overal ter wereld hetzelfde. OAK leest die in `OAK_TIMEZONE`.
- **Betrouwbaarheid:** de gegevens zijn niet officieel en kunnen fouten bevatten of later veranderen. Een advies dat erop rust, heeft daarom hooguit een gemiddelde betrouwbaarheid. Kan OAK de naam van een uitgelichte Pokémon niet aan een soort uit de Game Data koppelen, dan toont de eventpagina dat en levert dat event geen hold op.
- **Updates:** standaard iedere 12 uur (`OAK_EVENTS_AUTO_UPDATE`, `OAK_EVENTS_UPDATE_INTERVAL_HOURS`). De eigenaar kan ook op **Komende events** bijwerken. Een download wordt eerst gecontroleerd. Een mislukte of ongeldige download laat de vorige events staan en toont de fout op die pagina. Een lege lijst telt ook als ongeldig, want dan zouden alle regels voor *even bewaren* vervallen.

## Sprites

OAK levert geen Pokémon-afbeeldingen mee (ADR-0020). Standaard toont OAK een eigen badge met het Pokédex-nummer in de kleur van het type.

De eigenaar kan in de instellingen een externe spritebron aanzetten. De standaardkeuze is:

```
https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{shiny_path}{dex}.png
```

De browser laadt de afbeeldingen dan rechtstreeks bij die bron. OAK slaat ze niet op en verspreidt ze niet.

Over de licentie van die repository, gecontroleerd op 23 oktober 2026:

- Het `package.json` van PokeAPI/sprites noemt de ISC-licentie.
- De repository heeft geen licentiebestand.
- De README noemt geen CC0 en geen auteursrecht van The Pokémon Company.
- De README vermeldt dat de sprites vanaf Let's Go Pikachu en Let's Go Eevee uit originele game-assets zijn gerenderd.

Pokémon-afbeeldingen zijn auteursrechtelijk beschermd door The Pokémon Company, los van welke licentie een repository noemt. Wie een spritebron aanzet, doet dat op eigen verantwoordelijkheid.

## Referentieprojecten

Deze projecten zijn bekeken als functionele referentie. OAK neemt er geen code, data of vormgeving uit over.

| Project | Waarvoor bekeken | Licentie |
|---|---|---|
| [PGSAccount](https://github.com/Akshat-Vasava/PGsharp-Pok-mon-GO-Multi-Tenant-Account-Manager) | De PGSharp-instellingen en de gewenste functies | Geen licentiebestand |
| [PokéGO Analyzer](https://github.com/Predi97/pogo-analyzer) | Hoe `PGSStats.json` is opgebouwd | De README noemt MIT, maar de repository bevat geen licentiebestand |
| [PokéAPI](https://github.com/PokeAPI/pokeapi) | Algemene soortinformatie | BSD-stijl licentie. Niet gebruikt voor Pokémon GO-mechanica |

## Testgegevens in de repository

- `fixtures/gamedata/` bevat een kleine deelverzameling van de Game Master en de PvPoke-bestanden: ongeveer vijftig soorten met hun vormen en aanvallen. Hij is gemaakt met `scripts/build_test_gamedata.py` en wordt alleen in tests gebruikt. Voor het PokeMiners-deel geldt dezelfde onduidelijke licentie als hierboven.
- `fixtures/pgsharp/PGSStats.sample.json` is een synthetische export, gemaakt met `scripts/generate_sample_export.py`. Hij bevat geen echte accountgegevens.
- Nederlandse namen van types en items zijn eigen vertalingen in de code van OAK.

## Updates en onbereikbaarheid

- OAK controleert standaard iedere 24 uur of er nieuwe Game Data is (`OAK_GAMEDATA_AUTO_UPDATE`, `OAK_GAMEDATA_UPDATE_INTERVAL_HOURS`). De controle vergelijkt eerst alleen de ETags. Een download volgt alleen als er iets veranderd is.
- Met **Controleren op updates** vraagt de eigenaar de ETags en de datum van de nieuwste Game Master op, zonder download. OAK bewaart het resultaat, zodat de pagina blijft tonen wanneer er is gecontroleerd, van wanneer de nieuwste Game Master is en of je die al hebt. Ook een geslaagde update werkt dat resultaat bij.
- Iedere nieuwe dataset wordt gecontroleerd voordat hij actief wordt. Er moeten minstens 800 soorten, 1.000 vormen, 200 aanvallen en 80 CP-multipliers in staan. Een dataset die daar niet aan voldoet, wordt opgeslagen als mislukt. De actieve versie blijft dan in gebruik.
- Is een bron niet bereikbaar, dan werkt OAK door met de actieve versie en toont de fout op **Beheer → Game Data**.
- De drie nieuwste bruikbare versies blijven bewaard. Je kunt er op **Beheer → Game Data** naar terug.
- Zonder internet kun je de bestanden elders downloaden en daar uploaden. OAK controleert ze dan op dezelfde manier.
- Na een wissel van versie berekent OAK de afgeleide gegevens en alle analyses opnieuw. Ieder advies vermeldt de versie waarmee het is berekend.

De bron-URL's zijn aan te passen met `OAK_GAMEDATA_POKEMINERS_URL` (de Game Master, ondanks de naam) en `OAK_GAMEDATA_PVPOKE_BASE_URL`, bijvoorbeeld voor een eigen spiegel. OAK haalt alleen openbare bestanden op, met een herkenbare user-agent, en omzeilt geen toegangslimieten.

Iedere download gaat over https. Een bestand van de Game Data mag hoogstens 150 MB zijn, de eventkalender hoogstens 5 MB. OAK stopt bij die grens, ook als de server de grootte niet vooraf meldt. Een doorverwijzing volgt OAK alleen naar https op dezelfde host, en hoogstens vijf keer. Bij een dataset legt OAK het adres vast waar de inhoud echt vandaan kwam.
