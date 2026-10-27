# Analyse-engine

Dit document beschrijft hoe OAK rekent. Alles is deterministisch: dezelfde export, dezelfde Game Data en dezelfde instellingen geven altijd hetzelfde advies. Spelmechanica komt uit de actieve Game Data-versie (ADR-0017). Elk advies vermeldt de engineversie en de Game Data-versie waarmee het is berekend.

De code staat in `backend/app/analysis` (berekeningen) en `backend/app/recommendations` (cleanup). Beide mappen bevatten pure Python zonder database of webframework.

## Basisformules

```
CP = max(10, floor((Atk + IVa) · √(Def + IVd) · √(Sta + IVs) · CPM² / 10))
HP = max(10, floor((Sta + IVs) · CPM))
statproduct = (Atk + IVa) · CPM · (Def + IVd) · CPM · HP
```

De CP-multiplier per level komt uit de Game Data. Het level van een Pokémon leidt OAK af uit de multiplier in de export, met een kleine marge omdat PGSharp die als 32-bits getal opslaat.

## PvP-IV-rang

Voor iedere vorm en iedere league berekent OAK alle 4096 IV-combinaties. Per combinatie zoekt OAK het hoogste toegestane level waarbij de CP onder de limiet van de league blijft, en berekent het statproduct op dat level. De combinaties worden gerangschikt op statproduct. Gelijke waarden delen een rang (1, 2, 2, 4). Het maximale level is een instelling: standaard 50, met Best Buddy 51.

OAK houdt drie dingen uit elkaar:

- De **IV-rang** zegt hoe goed de IV's zijn binnen de soort, van 1 tot 4096.
- De **soortrang** komt uit de PvPoke-rankings en zegt hoe sterk de soort is in die league.
- De **inzetbaarheid** zegt of dit exemplaar nu bruikbaar is, na power-ups of na evolutie.

Inzetbaarheid heeft vijf waarden. *Direct inzetbaar* betekent dat de huidige CP minstens 95 procent is van de beste CP binnen de limiet (instelbaar). *Na power-up* en *na evolutie* spreken voor zich. *Niet geschikt* betekent boven de limiet of al boven het optimale level. *Onbekend* betekent dat het level ontbreekt.

Voor evoluties rekent OAK met dezelfde IV's op de geëvolueerde vorm, en vermeldt het de candy- en itemkosten uit de Game Data.

## Cups

Naast de drie leagues kent OAK de cups die PvPoke op zijn site toont, zoals de Fantasy Cup (ADR-0027). Bij het bijwerken van de Game Data past OAK de regels van iedere cup toe zoals PvPoke dat doet: welke types, welke soorten en welke vormen mee mogen, en welke juist niet. Een cup met regels die OAK niet kan toepassen, laat OAK weg.

De analyse van een cup werkt als die van een league. OAK neemt alleen doelen mee die de cup toelaat, ook na evolutie. Een Eevee verschijnt in de Fantasy Cup dus als toekomstige Sylveon, en niet als Vaporeon. Heeft een cup een levelgrens, zoals level 50 in de Little Cup, dan rekent OAK daar niet boven. De soortrang komt uit de ranglijst van PvPoke voor die cup. Ontbreekt die ranglijst, dan sorteert OAK alleen op IV-rang en zegt dat erbij.

Een Shadow Pokémon telt als de Shadow-vorm, want sommige cups sluiten Shadow Pokémon uit. Een vorm die PvPoke niet kent, kan OAK niet toetsen en blijft buiten de cup. Cups tellen niet mee in het cleanupadvies.

## Power-up-kosten

Stardust en candy per halve level komen uit de Game Data. Shadow kost 20 procent meer stardust en candy, Purified 10 procent minder. Lucky halveert alleen de stardust. Het spel documenteert niet hoe gebroken candy wordt afgerond. OAK rondt naar boven af, zodat een kostenraming nooit te laag uitvalt.

## Aanvallen

Voor iedere aanval bepaalt OAK of hij via een normale TM, alleen via een Elite TM, als legacy-aanval of helemaal niet meer te krijgen is. Het movesetadvies volgt de PvPoke-ranking. Vraagt die een Elite TM die je volgens de instellingen niet hebt, of een aanval die niet meer te krijgen is, dan zoekt OAK de meest gebruikte aanvallen die wel met een normale TM te krijgen zijn, en meldt dat.

## Raidmodel

```
schade per aanval = floor(0,5 · kracht · aanval / verdediging · STAB · effectiviteit) + 1
aanval            = (basis-Attack + Attack-IV) · CPM · Shadow-bonus
cyclus-DPS        = (n · snelle schade + geladen schade) / (n · duur snel + duur geladen)
n                 = energiekosten geladen aanval / energie per snelle aanval
```

Tegen een gekozen baas rekent OAK met de verdediging van die baas, voor de raidpositie met de mediaan van alle soorten. In beide gevallen op ongeveer level 40 met 15 Defense-IV. Het model negeert energie door schade, ontwijken, weer en de aanvallen van de baas. Het rangschikt aanvallers ten opzichte van elkaar en voorspelt geen gevechtsuitkomst.

### Raidpositie

Voor de bruikbaarheidsscore bepaalt OAK per aanvalstype waar een Pokémon zou staan tussen alle aanvallers van dat type.

Het vergelijkingsveld bevat iedere vorm uit de Game Data, op het hoogste normale level met 15 Attack-IV, met de beste snelle en geladen aanval van dat type. Alle aanvallen tellen mee, ook Elite TM- en legacy-aanvallen. Soorten die als Shadow bestaan, staan er twee keer in, gewoon en als Shadow. Mega-vormen staan niet in het veld, omdat ze tijdelijk zijn.

Voor de eigen Pokémon rekent OAK met de eigen Attack-IV, de Shadow-bonus als die geldt, en alleen de aanvallen die hij echt kan krijgen. Dat zijn zijn huidige aanvallen (zolang hij niet evolueert), de normale TM-pool en de Elite TM-pool als je Elite TM's hebt. Ook iedere vorm waarin hij kan evolueren telt mee. Andere vormen van dezelfde soort tellen niet als concurrent.

Het model kijkt alleen naar schade per seconde, niet naar hoe lang een aanvaller overleeft. Kwetsbare aanvallers met veel Attack komen daardoor wat gunstiger uit dan in rankings die ook overleving meewegen. Voor typen met weinig sterke aanvallers, zoals Fee, is een hoge plaats makkelijker te halen.

## Max Battles

Welke aanval een Pokémon in een Max Battle gebruikt, hangt af van zijn vorm.

- Een Dynamax-Pokémon gebruikt de Max-aanval van het type van zijn snelle aanval. Dat type en de naam komen uit `BREAD_MOVE_MAPPING_SETTINGS` in de Game Master.
- Een Gigantamax-Pokémon gebruikt altijd zijn eigen G-Max-aanval, ongeacht zijn snelle aanval. Een Gigantamax Charizard met Air Slash valt dus aan met G-Max Wildfire, van het type Vuur. Welke G-Max-aanval bij welke soort en vorm hoort, staat in `SOURDOUGH_MOVE_MAPPING_SETTINGS`.

De Game Master bevat geen leesbare namen voor deze aanvallen. OAK leidt de naam af van de effectnaam (`gmax_wildfire` wordt G-Max Wildfire), waardoor de schrijfwijze soms afwijkt, zoals G-Max Goldrush in plaats van G-Max Gold Rush.

Staat de G-Max-aanval van een Pokémon niet in de actieve Game Data, dan is het aanvalstype `onbekend`. OAK vermeldt dan waarom en rekent voor die Pokémon geen effectiviteit uit. Het valt nooit terug op het type van de snelle aanval.

## Gymverdedigers

Een goede gymverdediger vangt veel schade op voordat hij flauwvalt. Hoe langer hij dat volhoudt, hoe meer aanvallen een aanvaller nodig heeft.

```
verdedigingswaarde = effectieve Defense · HP
effectieve Defense = (basis-Defense + Defense-IV) · CPM · Shadow-factor
HP                 = floor((basis-Stamina + Stamina-IV) · CPM)
```

De schade per aanval hangt af van aanval gedeeld door Defense. Het aantal aanvallen dat nodig is, groeit daardoor met Defense maal HP. De Shadow-factor voor Defense komt uit de Game Data (`shadowPokemonDefenseBonusMultiplier`). OAK toont de waarde als getal van 0 tot 100. Op 100 staat de sterkst mogelijke verdediger uit de Game Data, op het hoogste normale level met perfecte IV's. Met de huidige Game Master is dat Blissey.

Of een Pokémon in een gym mag, staat per vorm in de Game Master (`isDeployable`). Legendary, Mythical en Ultra Beasts mogen meestal niet, maar er zijn uitzonderingen, zoals Meltan en Melmetal. OAK volgt de Game Data en heeft daarvoor geen eigen lijst. Kent de actieve dataset dat veld nog niet, dan toont OAK geen lijst maar vraagt het om de Game Data bij te werken.

Iedere soort mag maar één keer in dezelfde gym. OAK toont daarom per soort alleen het sterkste exemplaar, met het aantal andere exemplaren van die soort.

Wat OAK niet meeneemt:

- De eigen aanvallen van de verdediger.
- Het verlies van motivatie. Hoe snel dat gaat, staat niet in de Game Data. Volgens metingen uit de community gaat het sneller bij een hogere CP.

Staat een Pokémon nu in een gym, dan toont het overzicht dat. OAK leest dat uit de export (`deployedFortId`) en bewaart alleen ja of nee, nooit welke gym (ADR-0026). Met een echte export is gecontroleerd dat PGSharp dat veld vult en dat het label klopt.

## Purify

Purify zet een Shadow Pokémon op je trainerlevel, met een maximum van level 25, als hij daaronder zat. Iedere IV krijgt er 2 punten bij, tot 15. Frustration wordt Return. Die regels staan niet in de Game Master of bij PvPoke. OAK levert ze zelf aan, met bron en datum, en neemt ze op in de dataset (ADR-0022). De kosten van purify komen wel uit de Game Master.

Op de detailpagina van een Shadow Pokémon kies je tussen *Als Shadow* en *Na purify*. De battle-analyse, de evoluties en de power-ups rekenen dan met het level, de IV's en de aanvallen na purify, en met de lagere kosten voor een Purified Pokémon. Is purify je geplande actie, dan staat *Na purify* vooraan.

Purify is niet terug te draaien en een level kun je niet verlagen. Een Shadow Machop met 4/13/5 op level 8 wordt na purify een Machop van level 25 met 6/15/7. Laat je die evolueren, dan krijg je een Machoke van 1355 CP en een Machamp van 2066 CP. Die Machamp kan niet meer in Great League. Als Shadow had dezelfde Machop een Machamp van 639 CP opgeleverd, die je tot level 18,5 kunt opwaarderen.

Is je trainerlevel onbekend, dan gaat OAK uit van trainerlevel 25 of hoger en zegt dat erbij. Het cleanupadvies beoordeelt een Pokémon zoals hij nu is.

## Pokédex

De Pokédex zoekt in de actieve Game Data, op naam of op Pokédex-nummer. Hoofdletters, accenten en leestekens tellen niet mee, dus `flabebe` vindt Flabébé. Je hoeft een Pokémon niet zelf te hebben om hem op te zoeken.

Per vorm toont OAK de types, de basiswaarden, de buddy-afstand, of hij te ruilen is en in een gym mag, de kosten van een tweede charged-aanval en van purify, en de aanvallen met Elite TM en legacy. De CP met 15/15/15 staat erbij voor level 20 (raids en onderzoek), level 25 (met weerbonus), level 40 en het hoogste normale level. De plaats van de soort per league komt van PvPoke, en de plaats als gymverdediger is dezelfde rangorde als bij de gymverdedigers hierboven.

De Game Master heeft voor veel soorten een basisvorm naast de vorm `NORMAL`. Dat is dezelfde Pokémon. De Pokédex toont er één van en zoekt naar allebei.

Met een gekozen traineraccount zie je ook wat je collectie ermee kan:

- Hoeveel je van deze soort hebt, in welke vorm dan ook. Een andere vorm dan de gekozen vorm krijgt een label.
- Welke Pokémon uit je collectie ernaartoe kunnen evolueren, met de stappen, de candy, het item en de voorwaarden zoals in de evolutieplanner. De CP na evolutie rekent OAK uit met het level en de IV's van dat exemplaar. De sterkste uitkomst staat bovenaan.
- Of je het evolutie-item in je tas hebt. Dat aantal komt uit de export. Zit er geen itemtas in de import, dan zegt OAK dat het aantal onbekend is.
- Hoeveel candy je voor de familie hebt. PGSharp exporteert geen candy. Heb je het zelf ingevuld bij *Stardust & Candy*, dan toont OAK dat getal, anders meldt hij dat het onbekend is.

## Cleanup-advies

ADR-0019 legt de keuzes vast. Iedere Pokémon wordt geanalyseerd en vergeleken, ook beschermde, favoriete en vintage Pokémon. Bescherming bepaalt alleen de uiteindelijke status.

### Bruikbaarheidsscore (0 tot 100)

De bruikbaarheidsscore is de feitelijke waarde van dit exemplaar in gevechten. Favorietenstatus, vangstjaar en andere verzamelkenmerken tellen niet mee.

Per league neemt OAK het hoofddoel: de sterkste soort die de Pokémon kan worden (laagste PvPoke-soortrang), met zijn IV-rang daarvoor.

```
leaguewaarde = 100 · soortgewicht · IV-kwaliteit · movesetfactor
IV-kwaliteit = 1 − ln(IV-rang) / ln(4096)
```

IV-kwaliteit is 1 bij rang 1, 0,5 bij rang 64 en 0 bij rang 4096. De logaritmische schaal weerspiegelt dat het verschil tussen rang 1 en 10 veel groter is dan tussen 3000 en 3010.

Het soortgewicht is 1 tot en met soortrang 25 (`species_rank_full`) en loopt daarna lineair af tot 0 bij soortrang 150 (`meta_rank_threshold`). Een soort zonder PvPoke-ranking krijgt gewicht 0.

De movesetfactor is 0,9 als de beste aanvallen een Elite TM of een legacy-aanval vragen die deze Pokémon niet heeft. Kent hij die aanval al, dan blijft de factor 1.

```
raidwaarde = 100 · max(0, 1 − (raidpositie − 1) / 25)
```

Plaats 1 telt volledig, de waarde loopt lineair af tot 0 na plaats 25 (`raid_top_n`).

```
gymwaarde = 100 · max(0, 1 − (gympositie − 1) / 20)
```

De gympositie is de plaats die dit exemplaar, of een vorm waarin het kan evolueren, zou innemen tussen alle vormen die in een gym mogen. OAK vergelijkt Defense maal HP (zie *Gymverdedigers*) op het ingestelde maximale level met de eigen IV's, tegen ieder ander op het hoogste normale level met perfecte IV's. Andere vormen van dezelfde soort tellen niet mee. De waarde loopt lineair af tot 0 na plaats 20 (`gym_top_n`, ADR-0026).

De bruikbaarheidsscore is de hoogste van de league-, raid- en gymwaarden, niet de som. Dezelfde IV's tellen in iedere league mee, en optellen zou ze dus meerdere keren laten meewegen. De interface toont alle deelwaarden en welke de doorslag gaf.

### Bewaarscore (0 tot 100)

De bewaarscore zegt hoeveel reden er is om dit exemplaar te bewaren. OAK telt punten op en kapt af op 100. Iedere eigenschap telt één keer. IV's tellen alleen via de bruikbaarheid mee.

| Onderdeel | Standaard | Instelling |
|---|---|---|
| Bruikbaarheid | 45 procent van de bruikbaarheidsscore | `keep_weight_battle` |
| Beste of enige exemplaar van soort, vorm en Shadow-status | 20 | `keep_points_best_copy` |
| Favoriet | 25 | `keep_points_favorite` |
| Shiny | 15 | `keep_points_shiny` |
| Lucky | 10 | `keep_points_lucky` |
| Legendary, Mythical of Ultra Beast | 10 | `keep_points_rarity` |
| Kostuum | 10 | `keep_points_costume` |
| Speciale achtergrond | 10 | `keep_points_location_card` |
| Event-Pokémon | 10 | `keep_points_event` |
| Dynamax of Gigantamax | 10 | `keep_points_max` |
| XXL | 10 | `keep_points_xxl` |
| XXS | 5 | `keep_points_xxs` |
| Mega-voortgang | 5 | `keep_points_mega` |
| Bijzondere kenmerken samen hoogstens | 30 | `keep_traits_cap` |
| Bijnaam | 5 | `keep_points_nickname` |
| Eigen plan in OAK (niet 'overzetten') | 10 | `keep_points_planned` |

"Beste exemplaar" volgt uit een vaste volgorde binnen de groep: eerst bruikbaarheid, dan IV-percentage, dan CP.

XXL en XXS zijn de zeldzaamste groottes. Bij een showcase op een PokéStop maakt een XXL de meeste kans, en een XXS heeft vooral waarde voor een verzameling. Daarom krijgt een XXL meer punten dan een XXS. De grootte telt net als de andere bijzondere kenmerken alleen als punten mee. Ze is geen harde bescherming en telt niet mee in de bruikbaarheid, want ze verandert niets aan CP, IV's of aanvallen. OAK leest de grootte uit het veld `size` van de export: 1 is XXS en 5 is XXL. Dat 1 voor XXS staat, is gecontroleerd met een echte export en het spel. Voor 5 volgt het uit dezelfde nummering. Een onbekende grootte geeft geen punten.

### Harde bescherming

Harde bescherming staat los van beide scores. Een Pokémon met een harde reden krijgt altijd `PROTECT`, ook bij een lage bewaarscore. Harde redenen zijn:

- Vintage: gevangen in 2016, 2017, 2018 of 2019 (vaste regel, niet uit te zetten).
- Handmatig beschermd in OAK.
- Een in-game tag die je als beschermend hebt ingesteld.
- De instelbare regels voor shiny, lucky, hundo, achtergrond, kostuum, Mythical, Legendary, Ultra Beast, Shadow, Purified, Dynamax, Gigantamax, event, bijnaam en mega-voortgang.

Zet je zo'n regel uit, dan telt het kenmerk alleen nog als punten in de bewaarscore.

### Van scores naar status

OAK beslist in deze volgorde:

1. Een status die je zelf hebt ingesteld, gaat voor. Heft die de bescherming van een vintage Pokémon op, dan blijft een waarschuwing zichtbaar.
2. Een harde reden geeft `PROTECT`.
3. Zonder Game Data, zonder IV's of level, of bij een onbekende soort geeft OAK `UNKNOWN`.
4. De beste kandidaat voor een league-doel, het beste Master League-exemplaar, de beste raid-aanvaller binnen relevante soorten en de beste gymverdediger binnen de beste verdedigerssoorten krijgen `KEEP`, of `BUILD` als ze nog power-ups of een evolutie nodig hebben en hun IV-rang goed genoeg is (`build_iv_rank_threshold`).
5. Een bewaarscore vanaf 70 (`keep_threshold`) geeft `KEEP`.
6. Goede PvP-IV's (rang tot 100) terwijl er een beter exemplaar is, een eigen reviewverzoek of een onzekere vorm geven `REVIEW`.
7. Een bewaarscore vanaf 40 (`review_threshold`) geeft `REVIEW`.
8. Daaronder volgt `TRANSFER_CANDIDATE`.

Daarna volgen drie correcties:

- Het beste exemplaar van iedere groep blijft altijd bewaard, en er blijven minstens `keep_min_per_species` exemplaren. Zo heeft iedere transfer-kandidaat een beter of gelijkwaardig exemplaar dat blijft.
- Een transfer-kandidaat wordt `REVIEW` als hij favoriet is, als zijn vangstdatum onbekend is, als hij nu in een gym staat, of als de laatste import niet volledig was.
- Bij iedere transfer-kandidaat en ieder te beoordelen exemplaar noemt OAK het betere exemplaar dat bewaard blijft en waarin het beter is. Bij een vintage Pokémon noemt OAK ter vergelijking het nieuwere exemplaar dat beter is voor gevechten.

### Komende events

Na de correcties kijkt OAK naar de eventkalender (ADR-0021). Dat gebeurt alleen als `use_events` aan staat, en alleen voor events die nog niet voorbij zijn en binnen `event_hold_days` dagen beginnen (standaard 14).

- Een transfer-kandidaat uit de evolutielijn van een Pokémon met een Community Day wordt `KEEP` tot na het event. Tijdens een Community Day geeft evolueren vaak een speciale aanval.
- Een event dat je zelf toevoegt, houdt de evolutielijnen van de gekozen Pokémon op dezelfde manier vast.
- Een Pokémon die al `REVIEW` is, houdt die status en krijgt de eventreden erbij.
- Komt er een event met dubbele Transfer Candy aan, dan krijgt iedere overgebleven transfer-kandidaat de tip om daarop te wachten.
- Een status die je zelf hebt ingesteld, gaat altijd voor.

Iedere eventreden noemt het event, de periode, de bron, de versie van de eventgegevens en een link. De gegevens zijn niet officieel, dus de betrouwbaarheid van zo'n advies is hooguit *Gemiddeld*. Een event dat je negeert, telt voor dat traineraccount niet mee. Na afloop van een event vervalt de hold vanzelf, omdat OAK de analyse opnieuw berekent zodra een event binnen de termijn komt of voorbij is.

### Transferlijsten

OAK zet zelf nooit iets over. De actielijst is een hulpmiddel om in het spel af te werken.

- Een handmatig beschermde Pokémon komt nooit op de lijst.
- Een vintage Pokémon komt er alleen op als je de bescherming bij die ene Pokémon hebt opgeheven en het daarna nog eens per Pokémon bevestigt. Een bulkactie slaat vintage Pokémon altijd over.
- Een favoriet, een Pokémon met onbekende vangstdatum en een Pokémon met een andere harde bescherming vragen een bevestiging per Pokémon.
- De harde bescherming volgt uit de actuele gegevens van de Pokémon en de regels van het account, niet uit de opgeslagen analyse. Ook vlak na een import, als de analyse nog niet klaar is, geldt ze dus al.
- Een bevestiging geldt voor de concrete redenen van dat moment: favoriet, onbekende vangstdatum, vintage, iedere regel afzonderlijk (zoals shiny of bijnaam) en iedere beschermende tag met zijn tag-ID.
- OAK controleert de bescherming opnieuw bij het lezen, exporteren en afronden van de lijst. Komt er een reden bij die niet in je bevestiging zat, dan houdt OAK de Pokémon tegen, ook als hij al om een andere reden beschermd was. Een tweede beschermende tag naast een eerste vraagt dus opnieuw om bevestiging. De Pokémon staat dan niet in de zoekteksten en niet op de checklist, tot je hem opnieuw bevestigt of de nieuwe reden verdwijnt. Bij de vraag noemt OAK wat er nieuw is.
- Valt een reden weg, dan blijft de bevestiging voor de overige redenen gelden.

### Betrouwbaarheid

*Hoog* betekent een exacte vorm uit de Game Data na een volledige import. *Gemiddeld* geldt voor een review uit stap 6. *Laag* betekent ontbrekende gegevens, een vorm die op de standaardvorm is teruggevallen, of een gedeeltelijke laatste import.

## Herberekening

Een analyse is een projectie en kan altijd opnieuw worden berekend. OAK berekent opnieuw na iedere import, na een wijziging van regels of OAK-gegevens, na een Game Data-wissel, als een event binnen de termijn komt of voorbij is, en bij het starten als de engineversie is veranderd. De huidige engineversie is `cleanup-2.5`.

## Controle op een echte export

`backend/tests/test_real_export.py` controleert de regels op een echte export met de actuele Game Data. De test draait alleen als `OAK_TEST_REAL_EXPORT` naar een `PGSStats.json` wijst en heeft internet nodig. Een echte export is persoonlijke data en hoort niet in de repository.
