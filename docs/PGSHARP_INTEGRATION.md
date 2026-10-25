# PGSharp-koppeling

OAK haalt de gegevens van je Pokémon GO-account uit de functie **Export Account Data** van PGSharp. Dat kan op twee manieren, die dezelfde verwerking gebruiken:

- **Webhook.** PGSharp stuurt de export naar een persoonlijke URL van OAK.
- **Upload.** Je uploadt het bestand `PGSStats.json` dat PGSharp lokaal opslaat.

PGSharp is een niet-officiële Pokémon GO-client. Het gebruik ervan valt buiten de gebruiksvoorwaarden van Niantic en kan gevolgen hebben voor je account. OAK zelf vraagt nooit om je Pokémon GO-inloggegevens, logt nergens in en stuurt niets naar het spel.

## Wat geverifieerd is

| Onderdeel | Status |
|---|---|
| Lokaal opgeslagen export (`PGSStats.json`) | **Geverifieerd** met een echte export van oktober 2026: 974 Pokémon en 9 eieren, volledig ingelezen zonder meldingen. |
| Verzending via de webhook | **Nog niet geverifieerd.** Er is nog geen echt verzoek van PGSharp ontvangen. OAK accepteert daarom veel varianten en heeft een diagnosemodus om het eerste echte verzoek vast te leggen. |
| Knop *Test Connection* | **Bestaat**, gezien in PGSharp op 23 oktober 2026. Wat de test precies verstuurt, is niet vastgesteld. Tot deze versie gaf OAK er een `400` op. |
| Moment van verzenden | Volgens de PGSAccount-documentatie bij iedere login in PGSharp. Niet zelf vastgesteld. OAK noemt de synchronisatie daarom nooit realtime. |

Werkt de webhook bij jou, of juist niet? Zet dan de diagnosemodus aan (zie hieronder) en deel de structuursamenvatting van de import. Die bevat alleen veldnamen en typen, geen waarden.

## Welke PGSharp-versie

Je hebt een PGSharp-versie nodig met **Settings → Export Account Data (Beta)**. Volgens de PGSAccount-documentatie heeft die twee opties:

- *Save data to local file (on every login)*, voor de upload.
- *Send data to server (on every login)*, voor de webhook.

Welke versienummers deze functie hebben, is niet vastgesteld. De namen in het menu kunnen per versie verschillen.

## Instellen

1. Maak in OAK een traineraccount aan onder **Beheer → Traineraccounts**.
2. Open **Beheer → PGSharp Sync** en klik op **Webhook-URL maken**.
3. Kopieer de URL meteen. OAK bewaart alleen een hash van het token en kan de URL later niet meer tonen.
4. Open in PGSharp **Settings → Export Account Data** en zet *Send data to server* aan. Plak de URL als serveradres.
5. Druk op **Test Connection**. OAK antwoordt zonder iets te importeren, en onder **PGSharp Sync** toont *Laatst gebruikt* het moment van de test.
6. Log opnieuw in via PGSharp. Binnen enkele seconden verschijnt de import onder **PGSharp Sync**.

Is je URL uitgelekt, maak dan een nieuwe aan. De oude werkt direct niet meer. Met **Intrekken** schakel je de webhook helemaal uit.

### Handmatige upload

Zet in PGSharp *Save data to local file* aan en log in. Upload daarna `PGSStats.json` onder **Beheer → PGSharp Sync**, door het bestand naar het uploadvak te slepen of te kiezen. De upload hoort bij het traineraccount dat bovenaan is geselecteerd. Hoort de export bij een Pokémon GO-account dat al aan een ander traineraccount gekoppeld is, dan weigert OAK hem en noemt het juiste traineraccount.

## Het verzoek

```
POST /api/v1/ingest/pgsharp/oakwh_<id>_<geheim>
```

Het token bestaat uit een openbaar deel van 10 tekens om het record te vinden en een geheim deel van 256 bits. OAK vergelijkt de hash van het geheime deel in constante tijd.

OAK accepteert:

- JSON in de body, ook in een `multipart/form-data`-bestand.
- `Content-Encoding: gzip` of `deflate`, en gzip-inhoud zonder die header. De gecomprimeerde inhoud moet één volledige stream zijn, met einde en controlesom. Een afgebroken stream of gegevens erachter weigert OAK met `415`.
- UTF-8 of een andere tekenset uit `Content-Type`, met of zonder BOM.

| Antwoord | Betekenis |
|---|---|
| `202` met `"status": "queued"` | Ontvangen en in de wachtrij gezet. |
| `202` met `"status": "duplicate"` | Precies deze export was al ontvangen. Er verandert niets. |
| `200` met `"status": "connection_test"` | Een verbindingstest. Er is niets geïmporteerd. |
| `400` | De inhoud is geen leesbare JSON. De import staat als geweigerd in OAK, met de reden. |
| `404` | Onbekend of ingetrokken token. |
| `413` | Groter dan `OAK_MAX_IMPORT_MB` (standaard 64 MB). |
| `415` | Een niet-ondersteunde `Content-Encoding`. |
| `429` | Te veel verzoeken. Per webhook standaard 60 per uur. Per IP-adres blokkeert OAK na 20 ongeldige tokens 10 minuten lang. |

### Verbindingstest

Wat de knop *Test Connection* van PGSharp verstuurt, is niet gedocumenteerd. OAK behandelt daarom ieder verzoek van hoogstens 4 KB zonder export als verbindingstest. Daaronder vallen een leeg verzoek, gewone tekst, formuliervelden zonder bestand en JSON zonder lijst `pokemons`. Een echte export heeft altijd die lijst en is veel groter.

Tekst die met `{` of `[` begint maar geen geldige JSON is, blijft een fout. Dat lijkt op een kapotte export. Een verbindingstest maakt geen import aan, telt mee voor de limiet per webhook en komt in het logboek als `webhook connection test`, met methode, `Content-Type` en grootte. De inhoud komt nooit in het logboek.

## Structuur van een export

De geverifieerde export heeft vijf onderdelen op het hoogste niveau:

| Sleutel | Inhoud |
|---|---|
| `time` | Exportmoment als tekst, bijvoorbeeld `2026-10-23 12:00:00 CEST`. OAK kent alleen eenduidige tijdzoneafkortingen. Bij een onbekende afkorting blijft het exportmoment onbekend en volgt een waarschuwing. |
| `account` | Accountgegevens: naam, team, opslag, valuta en een versleutelde spelers-ID. |
| `player` | Trainerstatistieken: level, XP, kilometers, aantallen en gevechtsresultaten. |
| `items` | De item bag: `item` (nummer), `itemName` en `count`. |
| `pokemons` | Alle Pokémon en eieren. |

### Pokémon-velden

Alle velden in deze tabel kwamen voor in de geverifieerde export.

| Veld | In OAK |
|---|---|
| `id` | Unieke ID van de Pokémon, als tekst bewaard. In de echte export lag iedere ID boven 2^53, het grootste getal dat JavaScript exact kan opslaan. Een negatieve waarde zou OAK omrekenen naar de ongetekende waarde. Een kommagetal weigert OAK, omdat de ID dan al cijfers kwijt is. |
| `pokemonId` | Pokédex-nummer. |
| `pokemonDisplay.form`, `.formName` | Vorm. OAK koppelt die aan een vorm uit de Game Data. |
| `pokemonDisplay.costume`, `.gender`, `.shiny` | Kostuum, geslacht en shiny. |
| `pokemonDisplay.alignment` | 0 gewoon, 1 Shadow, 2 Purified. Alle drie gezien. |
| `pokemonDisplay.breadModeEnum` | 0 gewoon, 1 Dynamax. **Waarde 2 voor Gigantamax volgt uit de communityprotocollen en is nog niet in een echte export gezien.** |
| `pokemonDisplay.locationCard` | Speciale achtergrond. |
| `pokemonDisplay.currentTempEvolution`, `.megaEvolutionLevel` | Mega-stand. |
| `cp`, `stamina`, `maxStamina` | CP, huidige en maximale HP. |
| `individualAttack`, `individualDefense`, `individualStamina` | IV's. |
| `cpMultiplier`, `additionalCpMultiplier` | Waaruit OAK het level afleidt. |
| `move1`, `move2`, `move3` | Snelle aanval en de geladen aanvallen, als nummer. |
| `move2IsPurifiedExclusive` | Of de geladen aanval Return is na purifyen. |
| `numUpgrades` | Aantal power-ups. |
| `heightM`, `weightKg`, `size` | Lengte, gewicht en grootteklasse. |
| `pokeball` | Gebruikte bal. |
| `creationTimeMs` | Vangstmoment. Bepaalt het vangstjaar en daarmee of de Pokémon vintage is (ADR-0019). |
| `tradedTimeMs` | Ruilmoment, als de Pokémon geruild is. |
| `hatchedFromEgg`, `fromFort`, `originDetail`, `originEvents` | Herkomst. |
| `isLucky`, `favorite`, `nickname` | Lucky, favoriet en bijnaam. |
| `pokemonTagIds` | In-game tags, als tekst bewaard. De namen exporteert PGSharp niet. |
| `breadMoves` | Max Moves met level. |
| `hasMegaEvolved`, `megaEvolvedForms` | Mega-voortgang. |
| `buddyKmWalked`, `buddyCandyAwarded`, `battlesAttacked`, `battlesDefended` | Buddy- en gevechtsgegevens. |
| `limitedPokemonIdentifier` | Beperkte uitgave, bijvoorbeeld van een event. |
| `isEgg` | Eieren telt OAK mee in de opslag, maar niet als Pokémon. |

Andere velden zonder privacygevoelige naam bewaart OAK alleen als ze een waarde hebben die afwijkt van nul of leeg. Zo kan een latere versie ze nog interpreteren.

### Wat OAK niet bewaart

OAK verwijdert bij ontvangst, nog voor er iets op schijf komt:

- Locaties: `capturedS2CellId` en de coördinaten en ID's van gyms, PokéStops en stations.
- Namen en hashes van andere spelers: `ownerName`, `originalOwnerNickname`, `tradingOriginalOwnerHash`.
- Interne spelers-ID's en accountvelden die OAK niet gebruikt.
- Velden waarvan de naam op locatie, speler, account, apparaat, sessie of token wijst.

Dat geldt op ieder niveau en in iedere sectie van de export: account, speler, items en Pokémon, ook binnen geneste objecten en lijsten zoals gevechtsstatistieken en badges. Daar kijkt OAK per woord van de veldnaam, zodat `playerId` en `latitude` verdwijnen, maar `bonusIndividualAttack` blijft. Per sectie bewaart OAK alleen de velden die het leest, en iedere waarde daarvan gaat door hetzelfde filter, wat voor type het ook is.

Wordt het filter strenger, dan filtert OAK de nog bewaarde exports bij de eerstvolgende start één keer opnieuw. Ze hoeven dus niet eerst de bewaartermijn van `OAK_RAW_IMPORT_RETENTION_DAYS` uit te dienen.

De `obfuscatedPlayerId` uit de accountsectie bewaart OAK niet. OAK berekent er een sleutelgebonden vingerafdruk van (HMAC met de geheime sleutel van de installatie) en bewaart alleen die.

## Accountherkenning

Bij de eerste geslaagde import koppelt OAK het traineraccount aan de vingerafdruk van het Pokémon GO-account. Een latere export met een andere vingerafdruk weigert OAK: *Deze export hoort bij een ander Pokémon GO-account*. De trainernaam alleen is nooit genoeg om te koppelen.

Wissel je bewust van Pokémon GO-account, gebruik dan **Koppeling vergeten** bij het traineraccount.

## Volledig of gedeeltelijk

Een Pokémon die in een nieuwe export ontbreekt, markeert OAK alleen als *Niet meer in inventaris* als de import aantoonbaar volledig is. OAK noemt dat nooit "overgezet".

| Classificatie | Wanneer | Gevolg |
|---|---|---|
| Volledig | Geen van de onderstaande problemen. | Ontbrekende Pokémon zijn niet meer in inventaris. |
| Gedeeltelijk | Records zonder leesbare ID, een ontbrekende accountsectie, een gewijzigde trainernaam zonder vingerafdruk, een lege Pokémon-lijst of een verdachte daling. | Aanwezige Pokémon worden bijgewerkt, ontbrekende blijven staan. Er komt ook geen transferadvies. |
| Ongeldig | Geen Pokémon-lijst, geen enkel leesbaar record of een ander Pokémon GO-account. | Er verandert niets. |
| Verouderd | Ouder dan de laatst verwerkte export. | Er verandert niets. |
| Dubbel | Precies dezelfde inhoud als een eerdere export. | Er verandert niets. |

Een daling geldt als verdacht als er meer dan 25 Pokémon én meer dan 20 procent minder zijn dan in de huidige inventaris. Beide grenzen stel je per traineraccount in.

Was een gedeeltelijke import toch volledig, bijvoorbeeld na een grote opruimactie in het spel, dan kun je dat bij die import bevestigen. OAK verwerkt de export dan opnieuw als volledig.

## Diagnose

Bij iedere import legt OAK vast hoe het verzoek eruitzag: methode, `Content-Type`, compressie, tekenset, user-agent, grootte en de namen van de headers. Daarnaast maakt OAK een samenvatting van de structuur: de veldpaden met hun typen (maximaal 1.500 paden en 6 niveaus diep), de aantallen, en welke velden nieuw zijn of ontbreken ten opzichte van de geverifieerde export. Je ziet dit bij de details van een import.

Normaal kijkt OAK voor die samenvatting naar de eerste 200 records van iedere lijst. Met de diagnosemodus, die je onder **Beheer → PGSharp Sync** 24 uur aanzet, bekijkt OAK alle records, tot 20.000 per lijst. Dat helpt als een zeldzaam veld maar bij enkele Pokémon voorkomt.

De inhoud van de export legt OAK in geen van beide gevallen vast. Van de headers bewaart OAK alleen de namen. De enige uitzondering is de user-agent, die OAK ingekort tot 200 tekens bewaart om PGSharp-versies te kunnen herkennen.

## Bewaren van exports

Een ontvangen export bewaart OAK opgeschoond en gecomprimeerd in `/data/imports`, zodat een mislukte import opnieuw kan. Na `OAK_RAW_IMPORT_RETENTION_DAYS` (standaard 14) dagen verwijdert OAK het bestand. De resultaten van de import blijven staan.

## Problemen oplossen

| Probleem | Oplossing |
|---|---|
| Er verschijnt geen import | Controleer of OAK van buitenaf bereikbaar is op het adres uit de webhook-URL, en of je opnieuw hebt ingelogd in PGSharp. Kijk in het logboek van je reverse proxy of het verzoek binnenkwam. |
| `404` of "Onbekende webhook" | Het token is fout, ingetrokken of vervangen. Maak een nieuwe URL. |
| "Deze export hoort bij een ander Pokémon GO-account" | De export komt van een ander account dan het gekoppelde. Kies het juiste traineraccount, of gebruik **Koppeling vergeten** als je bewust wisselt. |
| De import is gedeeltelijk | Lees de reden bij de import. Klopt de export toch, bevestig hem dan als volledig. |
| "Ongeldige JSON" | Het bestand is afgebroken of beschadigd. Exporteer opnieuw. Upload bij twijfel het lokale bestand. |
| `413` | Verhoog `OAK_MAX_IMPORT_MB`, en de maximale verzoekgrootte van je reverse proxy. |
