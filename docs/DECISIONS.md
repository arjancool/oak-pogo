# Besluiten

Dit register bevat de besluiten van de eigenaar over OAK. Een besluit dat de architectuur raakt, krijgt ook een ADR in `docs/adr/`. Een geaccepteerd besluit verandert alleen via een nieuw besluit dat het vervangt.

DEC-001 en DEC-002 gingen over de orchestratie van de vorige versie. Ze zijn met DEC-008 vervallen en staan hier niet meer.

| ID | Datum | Beslisser | Besluit | Vervangt of botst met | Uitwerking | Status |
|---|---|---|---|---|---|---|
| DEC-003 | 2026-10-23 | Arjan Coolegem | OAK 2.0. PGSharp-export wordt de primaire databron. Stack wordt FastAPI, SQLite en React in één container. De Calcy IV-/PostgreSQL-implementatie gaat naar `archive/oak-v1/`. | ADR-0002, ADR-0004, ADR-0005, ADR-0006, ADR-0008, ADR-0011 en de frozen documentatiebaseline v1.0 versus de OAK 2.0-opdracht. | Superseding ADR-0012 t/m ADR-0018, nieuwe `CLAUDE.md` en `AGENTS.md`, oude baseline gearchiveerd. | Vastgesteld |
| DEC-004 | 2026-10-23 | Arjan Coolegem | Favorieten worden een zachte bescherming via de bewaarscore. Pokémon uit 2016–2019 zijn hard beschermd als vintage. Iedere Pokémon krijgt een bruikbaarheidsscore en een bewaarscore. | Regels `protect_favorites` en `protect_before_year` uit de eerste Cleanup-engine. | ADR-0019, engineversie `cleanup-2.0`, migratie `0002`. | Geaccepteerd |
| DEC-005 | 2026-10-23 | Arjan Coolegem | ADR-0018 wordt vervangen door ADR-0020. Het besluit over artwork blijft gelijk, de onjuiste licentiegegevens over de PokeAPI-sprites worden gecorrigeerd. | De context van ADR-0018 (CC0 en een vermelding van auteursrecht) versus de gecontroleerde repository `PokeAPI/sprites`. | ADR-0020, status van ADR-0018, verwijzingen in code en documentatie, melding in het instellingenscherm. | Geaccepteerd |
| DEC-006 | 2026-10-25 | Arjan Coolegem | Cleanupadvies houdt rekening met komende events via eventgegevens van LeekDuck (via ScrapedDuck) en deterministische regels, niet via een AI. | Een AI-oplossing versus eventgegevens met regels; ADR-0009 en de regel dat AI-uitvoer buiten de beslislogica blijft. | ADR-0021, eventbron, regels in de cleanup-engine, eventpagina, documentatie. | Geaccepteerd |
| DEC-007 | 2026-10-25 | Arjan Coolegem | Spelregels die niet in de Game Master of PvPoke staan, levert OAK aan in een klein supplement met bron en datum. De omzetting neemt ze op in iedere dataset. De eerste regels zijn die voor purify. | ADR-0017: spelmechanica komt uit de actieve dataset, niet uit constanten in de code. | ADR-0022, `supplement.py`, revisie 4 van de omzetting, purify-scenario op de detailpagina. | Geaccepteerd |
| DEC-008 | 2026-10-25 | Arjan Coolegem | De repository wordt openbaar. De oude implementatie, Hermes-Oak, de orchestratiebestanden en de vervangen ADR's gaan eruit. De openbare repository begint zonder de eerdere geschiedenis. | DEC-003: de oude implementatie bewaren in `archive/oak-v1/` en Hermes-Oak ongewijzigd laten. | ADR-0023, dit register verhuist naar `docs/DECISIONS.md`, verwijzingen bijgewerkt. | Geaccepteerd |

## DEC-003

- Decision-ID: DEC-003
- Datum en tijd: 2026-10-23, Claude Code-sessie
- Beslisser: Arjan Coolegem
- Vraag/conflict: de repository bevatte geaccepteerde ADR's voor Vue 3, PostgreSQL als bron van waarheid, event sourcing, CQRS, tenants en Calcy IV-matching. De OAK 2.0-opdracht vraagt React, SQLite, één container en PGSharp als primaire bron.
- Besluit: OAK 2.0 volgens de opdracht bouwen. De oude code en documentatie verplaatsen naar `archive/oak-v1/` in plaats van ze te verwijderen.
- Motivering: PGSharp levert per Pokémon een stabiele unieke ID, waardoor de Calcy-matchingproblematiek vervalt. Eén container met SQLite past bij een particuliere self-hosted installatie.
- In scope: nieuwe backend, frontend, documentatie, Docker en CI.
- Expliciet niet in scope: Hermes-Oak (`hermes-oak/`) en de orchestratiegovernance blijven ongewijzigd.
- Gesupersede bron: ADR-0002, ADR-0004, ADR-0005, ADR-0006, ADR-0008, ADR-0011 en `DOCUMENTATION-BASELINE-v1.0.md`.
- Benodigde repositorywijzigingen: zie ADR-0012 t/m ADR-0018.
- Einddatum of mergeblokkade: geen.
- Verificatiebewijs: laatste commit vóór de wijziging is `516f7d1`.

## DEC-004

- Decision-ID: DEC-004
- Datum en tijd: 2026-10-23, Claude Code-sessie
- Beslisser: Arjan Coolegem
- Vraag/conflict: met 860 favorieten in een collectie van 974 Pokémon beschermde de Cleanup-engine bijna alles en vergeleek hij die Pokémon niet meer.
- Besluit: favorieten krijgen extra bewaarpunten en worden nooit direct als transfer voorgesteld; vintage Pokémon (2016–2019) zijn hard beschermd maar worden volledig geanalyseerd; twee aparte scores voor bruikbaarheid en bewaren.
- Motivering: OAK moet de beste exemplaren helpen bewaren en overbodige exemplaren herkennen, zonder dat waardevolle oude Pokémon verloren gaan.
- In scope: Cleanup-engine, analyseservice, API, interface, instellingen en documentatie.
- Expliciet niet in scope: de andere harde beschermingsregels blijven standaard aan.
- Gesupersede bron: de regels `protect_favorites` en `protect_before_year` van engineversie `cleanup-1.0`.
- Benodigde repositorywijzigingen: zie ADR-0019.
- Einddatum of mergeblokkade: geen.
- Verificatiebewijs: `backend/tests/test_cleanup.py`, `backend/tests/test_cleanup_api.py` en de optionele `backend/tests/test_real_export.py`.

## DEC-005

- Decision-ID: DEC-005
- Datum en tijd: 2026-10-23, Claude Code-sessie
- Beslisser: Arjan Coolegem
- Vraag/conflict: ADR-0018 noemt de PokeAPI-spriterepository CC0 en zegt dat die repository expliciet het auteursrecht van The Pokémon Company vermeldt. Bij controle noemt het `package.json` ISC, is er geen licentiebestand en staat geen van beide beweringen in de README.
- Besluit: een nieuwe ADR-0020 vervangt ADR-0018. Het besluit blijft inhoudelijk gelijk, met de gecontroleerde licentiegegevens en de regel dat OAK een spritebron nooit vrij te gebruiken noemt.
- Motivering: een geaccepteerde ADR mag alleen via een nieuwe ADR veranderen, en een besluit hoort op juiste feiten te rusten.
- In scope: ADR-0020, de status van ADR-0018, verwijzingen in code en documentatie, `docs/DATA_SOURCES.md` en de melding in het instellingenscherm.
- Expliciet niet in scope: de werking van de spritebron, de standaardinstelling en de Content-Security-Policy.
- Gesupersede bron: ADR-0018.
- Benodigde repositorywijzigingen: zie ADR-0020.
- Einddatum of mergeblokkade: geen.
- Verificatiebewijs: `package.json`, README en het ontbreken van een licentiebestand in `PokeAPI/sprites` op branch `master`, gecontroleerd op 2026-10-23.

## DEC-006

- Decision-ID: DEC-006
- Datum en tijd: 2026-10-25, Claude Code-sessie
- Beslisser: Arjan Coolegem
- Vraag/conflict: het cleanupadvies houdt geen rekening met komende events. De vraag was of een AI dat kan oplossen.
- Besluit: geen AI in de beslissing. OAK haalt de eventkalender van LeekDuck op via ScrapedDuck en past deterministische regels toe: een tijdelijke hold voor Pokémon uit de evolutielijn van een komende Community Day, en een tip om met overzetten te wachten op dubbele Transfer Candy. Gebruikers kunnen events negeren en zelf toevoegen.
- Motivering: het tekort is informatie, niet rekenkracht. Regels op eventgegevens zijn uitlegbaar en testbaar, en ADR-0009 vraagt dat kernfunctionaliteit zonder AI werkt.
- In scope: ADR-0021, ophalen en bewaren van events, regels in de cleanup-engine, de eventpagina en de documentatie.
- Expliciet niet in scope: een AI-assistent, GO Battle League-cups en raidplanning.
- Gesupersede bron: geen.
- Benodigde repositorywijzigingen: zie ADR-0021.
- Einddatum of mergeblokkade: geen.
- Verificatiebewijs: `events.json` van ScrapedDuck en de gebruiksvoorwaarden in de README van `bigfoott/ScrapedDuck`, gecontroleerd op 2026-10-25.

## DEC-007

- Decision-ID: DEC-007
- Datum en tijd: 2026-10-25, Claude Code-sessie
- Beslisser: Arjan Coolegem
- Vraag/conflict: een gepurifyde Shadow Machop werd in het spel een Machoke van 1355 CP en een Machamp van 2066 CP, terwijl OAK 418 en 639 CP voorspelde. OAK rekende alleen met de Shadow-versie. Het level en de IV-bonus na purify staan niet in de Game Master of bij PvPoke, en ADR-0017 verbiedt spelregels als constanten in de code.
- Besluit: OAK levert spelregels die in geen van beide bronnen staan aan in een klein supplement met bron en datum. De omzetting neemt ze op in iedere dataset. De eerste regels zijn die voor purify.
- Motivering: zo komen alle spelregels nog steeds uit de actieve dataset, met versie en bron, en is de berekening na te rekenen.
- In scope: ADR-0022, `backend/app/gamedata/supplement.py`, revisie 4 van de omzetting, het purify-scenario in de battle-analyse, de evoluties en de power-ups.
- Expliciet niet in scope: een nieuwe cleanupstatus voor Pokémon die je wilt purifyen.
- Gesupersede bron: geen. ADR-0022 vult ADR-0017 aan.
- Benodigde repositorywijzigingen: zie ADR-0022.
- Einddatum of mergeblokkade: geen.
- Verificatiebewijs: `backend/tests/test_purify.py` rekent de Machop uit het spel na.

## DEC-008

- Decision-ID: DEC-008
- Datum en tijd: 2026-10-25, Claude Code-sessie
- Beslisser: Arjan Coolegem
- Vraag/conflict: de repository wordt openbaar, maar bevatte nog de oude implementatie in `archive/oak-v1/`, de losse projecten Hermes-Oak en `evidence/`, de orchestratiebestanden onder `docs/00-governance/` en ADR's die al vervangen waren.
- Besluit: die bestanden gaan uit de repository. Oude versies worden niet in een map bewaard. De openbare repository begint met één commit zonder de eerdere geschiedenis.
- Motivering: een openbare repository hoort alleen te bevatten wat OAK nu is. Oude versies blijven terug te vinden in de privérepository zolang de eigenaar die bewaart.
- In scope: ADR-0023, dit register, verwijzingen in `AGENTS.md`, `CHANGELOG.md`, `docs/ROADMAP.md`, `docs/DATA_SOURCES.md`, `.gitattributes` en `.dockerignore`.
- Expliciet niet in scope: geaccepteerde ADR's. Hun verwijzingen naar verwijderde ADR's en naar `archive/oak-v1/` blijven staan als geschiedenis (zie ADR-0023).
- Gesupersede bron: het deel van DEC-003 over `archive/oak-v1/` en Hermes-Oak.
- Benodigde repositorywijzigingen: zie ADR-0023.
- Einddatum of mergeblokkade: geen.
- Verificatiebewijs: de pull request met deze opschoning.

## Sjabloon

- Decision-ID:
- Datum en tijd:
- Beslisser:
- Vraag/conflict:
- Besluit:
- Motivering:
- In scope:
- Expliciet niet in scope:
- Gesupersede bron:
- Benodigde repositorywijzigingen:
- Einddatum of mergeblokkade:
- Verificatiebewijs:
