# Zoeken in de Pokémon Box

Het zoekveld van de Pokémon Box kent een eigen zoeksyntax. Die lijkt op de zoekfunctie van Pokémon GO, maar is niet hetzelfde. De verwerking staat in `backend/app/domain/query.py` en `backend/app/repositories/pokemon_query.py`.

## Termen combineren

Zet termen achter elkaar met een spatie of een `&`. Een Pokémon moet aan alle termen voldoen.

```
gyarados shiny cp>2500
gyarados&shiny&cp>2500
```

Een `!` voor een term keert hem om. `!favorite` geeft alles behalve favorieten.

Een komma voor "of", zoals in Pokémon GO, kent OAK niet. Hoofdletters maken niet uit. Je kunt hoogstens 20 termen gebruiken.

Een onbekend veld, zoals `onbekend:3`, of een ongeldige waarde, zoals `cp>abc`, geeft een foutmelding. Een los woord zonder veld zoekt OAK altijd als tekst in de naam. Een tikfout daarin geeft dus geen melding, maar gewoon geen resultaten.

## Getallen

Vergelijk een getal met `>`, `>=`, `<`, `<=`, `=` of `:`. Met `:` of `=` kun je ook een bereik geven, zoals `cp:1000-2000`. De grenzen tellen mee.

| Term | Betekenis |
|---|---|
| `cp` | CP |
| `hp` | Maximale HP |
| `iv` | IV-percentage, van 0 tot 100 |
| `atk`, `def`, `sta` | Losse IV's, van 0 tot 15. `hp_iv` is hetzelfde als `sta`. |
| `level`, `lvl` | Level |
| `year` | Vangstjaar in de tijdzone van OAK |
| `dex` | Pokédex-nummer |
| `great`, `gl` | IV-rang in de Great League, waarbij 1 de beste is |
| `ultra`, `ul` | IV-rang in de Ultra League |
| `bruikbaarheid`, `battle` | Bruikbaarheidsscore, van 0 tot 100 |
| `bewaar`, `keep` | Bewaarscore, van 0 tot 100 |

Er zijn ook drie korte vormen.

| Term | Betekenis |
|---|---|
| `#130` | Pokédex-nummer 130 |
| `2018` | Gevangen in 2018. Dit werkt voor ieder jaartal dat met 20 begint. |
| `15/15/15` of `ivs:15/15/15` | Precies deze IV's, in de volgorde aanval, verdediging en HP |

Een Pokémon zonder waarde voor het gekozen veld valt buiten iedere vergelijking. Zonder Game Data heeft een Pokémon bijvoorbeeld geen level en geen IV-rang. `great<=100` vindt hem dan niet, en `!great<=100` ook niet.

## Eigenschappen

| Term | Andere schrijfwijzen | Betekenis |
|---|---|---|
| `shiny` | | Shiny |
| `lucky` | | Lucky |
| `shadow` | | Shadow |
| `purified` | | Purified |
| `favorite` | `fav`, `favourite` | Favoriet in het spel |
| `legendary` | `legendarisch` | Legendary |
| `mythical` | `mythisch` | Mythical |
| `ultrabeast` | `ub` | Ultra Beast |
| `dynamax` | `dmax` | Dynamax of Gigantamax |
| `gigantamax` | `gmax` | Gigantamax. De waarde in de export is nog niet geverifieerd. |
| `costume` | `kostuum` | Met kostuum |
| `background` | `achtergrond`, `locationcard` | Met een achtergrond |
| `hundo` | `4*` | IV's 15/15/15 |
| `shundo` | | Shiny met IV's 15/15/15 |
| `nundo` | `0*` | IV's 0/0/0 |
| `traded` | `geruild` | Ooit geruild |
| `egg_hatched` | `hatched` | Uit een ei |
| `buddy` | | Heeft als buddy gelopen |
| `nicknamed` | | Heeft een bijnaam |
| `mega` | | Is ooit mega-geëvolueerd |
| `vintage` | | Gevangen in 2016, 2017, 2018 of 2019 |
| `unknown_date` | `datumonbekend` | Geen bruikbare vangstdatum. Ook een datum vóór 2016 telt als onbekend. |
| `new` | `nieuw` | Voor het eerst gezien bij de laatste synchronisatie. Bij de allereerste synchronisatie is niets nieuw. |
| `missing` | `verdwenen` | Niet meer in inventaris. Zonder statusfilter zoekt OAK dan ook buiten de huidige inventaris. |
| `protected` | `beschermd` | Handmatig beschermd in OAK, of met de cleanup-status Beschermd |
| `duplicate` | `dup`, `dubbel` | Er is nog een exemplaar van dezelfde vorm, met dezelfde Shadow- of Purified-stand, in de inventaris |
| `untagged` | | Heeft geen in-game tags |

`evolvable` en `evolueerbaar` bestaan nog niet als zoekterm. OAK geeft daarvoor een foutmelding. De Evolutieplanner toont welke evoluties mogelijk zijn.

## Tekst

Deze velden schrijf je als `veld:waarde`. Een `_` in de waarde staat voor een spatie, dus `move:hydro_pump` zoekt op "hydro pump".

| Term | Betekenis |
|---|---|
| `name:` | Soortnaam of bijnaam bevat de tekst |
| `form:` | Naam van de vorm bevat de tekst, bijvoorbeeld `form:alola` |
| `move:` | Een van de drie aanvallen bevat de tekst. OAK zoekt in de interne naam van de aanval, die Engels is. |
| `type:` | Een van de typen is precies deze waarde. Gebruik de Engelse naam, zoals `type:water` of `type:fighting`. |
| `family:` | De familie bevat de tekst, bijvoorbeeld `family:magikarp` |
| `tag:` | Een in-game tag met precies deze ID, of een OAK-tag waarvan de naam met de tekst begint |
| `status:` | De cleanup-status: `protect`, `build`, `keep`, `review`, `transfer_candidate` of `unknown` |
| `league:` | Er is een analyse voor deze league: `great`, `ultra` of `master` |

Een losse tekst zonder veld zoekt in de soortnaam, de bijnaam en de naam van de vorm. `gyara` vindt dus Gyarados.

## Voorbeelden

| Zoekopdracht | Resultaat |
|---|---|
| `magikarp !shiny !lucky` | Gewone Magikarp |
| `vintage dubbel` | Vintage Pokémon waarvan je nog een exemplaar hebt |
| `great<=50 !beschermd` | Sterke IV's voor de Great League, zonder harde bescherming |
| `status:transfer_candidate favorite` | Transfer-kandidaten die ook favoriet zijn. Normaal hoort die combinatie leeg te zijn, want een favoriet wordt nooit direct transfer-kandidaat. |
| `bewaar<40 !datumonbekend` | Lage bewaarscore, met een bekende vangstdatum |
| `type:dragon iv>=90 level<30` | Draken met goede IV's die nog power-ups kunnen krijgen |

## Zoekteksten voor in het spel

De actielijst van de Cleanup Manager maakt aparte zoekteksten in de syntax van Pokémon GO. Het spel kan niet op ID zoeken. Daarom gebruikt OAK per soort het Pokédex-nummer met de exacte CP van ieder exemplaar op de lijst, en sluit voor de zekerheid bijzondere Pokémon uit.

```
129&cp45,cp112&!favorite&!shiny&!lucky&!4*&!legendary&!mythical&!shadow&!costume
```

Boven iedere zoektekst staat welke Pokémon hij vindt, met naam en CP en de bijnaam als hij er een heeft. Bijvoorbeeld *Magikarp CP 45 · Magikarp CP 112*. De knop *Kopiëren* kopieert alleen de zoektekst.

Twee Pokémon van dezelfde soort met dezelfde CP zijn zo niet van elkaar te onderscheiden. Controleer daarom iedere Pokémon in het spel voordat je hem overzet. Deze teksten werken niet in het zoekveld van OAK.
