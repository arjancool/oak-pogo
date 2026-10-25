# Changelog

Alle noemenswaardige wijzigingen in OAK. De opbouw volgt [Keep a Changelog](https://keepachangelog.com/nl/1.1.0/) en de versies volgen [Semantic Versioning](https://semver.org/lang/nl/).

## [Onuitgebracht]

### Toegevoegd

- Op de detailpagina van een Shadow Pokémon kun je kiezen tussen *Als Shadow* en *Na purify*. De battle-analyse, de evoluties en de power-ups rekenen dan met het level en de IV's na purify. Zo zie je vooraf of een Pokémon na purify te sterk wordt voor Great League. De regels voor purify staan niet in de Game Master. OAK levert ze zelf aan, met bron (ADR-0022), en bouwt de Game Data daarvoor een keer opnieuw op.
- Het cleanupadvies houdt rekening met komende events (ADR-0021). Een transfer-kandidaat uit de evolutielijn van een Pokémon met een Community Day in de komende 14 dagen blijft bewaard tot na het event. Bij dubbele Transfer Candy krijg je een tip om te wachten. De kalender komt van LeekDuck.com via ScrapedDuck en wordt iedere 12 uur bijgewerkt. Onder **Pokémon → Komende events** kun je een event negeren of zelf een event toevoegen. De engineversie is nu `cleanup-2.1`, dus OAK berekent alle analyses een keer opnieuw.
- De eigenaar kan onder **Beheer → Instellingen → Gebruikers** het wachtwoord van een andere gebruiker opnieuw instellen. Die gebruiker wordt daarbij overal uitgelogd.

- Een overzicht van je beste gymverdedigers onder **Battles → Gymverdedigers**. Per soort staat je sterkste exemplaar, gerangschikt op Defense maal HP, met de redenen. Of een Pokémon in een gym mag, komt uit de Game Data. Na de update bouwt OAK de Game Data daarvoor een keer opnieuw op.

- Sorteren in de tabellen van de Great, Ultra en Master League, door op een kolomkop te klikken. Het sorteren gebeurt over alle geschikte Pokémon, en de keuze staat in de adresbalk.
- Sorteren in de raidtabel op naam, CP, DPS nu en de DPS met de beste moveset. Het sorteren gebeurt binnen de getoonde aanvallers, en het nummer blijft hun plek op DPS.
- Beveiligingscontroles in CI tegen de draaiende container, een scan op bekende kwetsbaarheden met Grype en een wekelijkse controle. Dependabot stelt iedere week updates voor.
- De actielijst toont per Pokémon of hij nog uitvoerbaar is. Een Pokémon die inmiddels beschermd is of een nieuwe bevestiging nodig heeft, staat niet in de zoekopdracht, de checklist of de uitvoerbare regels van de CSV.
- Een upload kan worden geannuleerd en stopt na tien minuten.
- `npm audit` in CI, die faalt bij een melding met ernst hoog of kritiek.

### Gewijzigd

- Een import vervangt de inventaris alleen als vaststaat dat de export bij het gekoppelde account hoort en wanneer hij is gemaakt. Anders is de import gedeeltelijk en verdwijnt er geen Pokémon. Zo'n import kun je na controle als volledig bevestigen.
- Bescherming op een transferlijst wordt berekend uit de actuele gegevens en regels, niet uit een analyse die nog kan ontbreken. OAK controleert hem opnieuw bij iedere keer lezen, exporteren en afronden.
- Bestaande actielijsten moeten opnieuw worden bevestigd voor favorieten, vintage Pokémon, Pokémon zonder vangstdatum en Pokémon met regelbescherming. De bevestiging wordt nu per Pokémon opgeslagen.
- OAK verwijdert locatie- en identiteitsvelden uit een export op iedere diepte.
- Registreren kan pas als er een eigenaar is.
- Publiceren van de image is de laatste stap van de CI-run en volgt alleen als alle controles voor die commit zijn geslaagd. `release.yml` is vervallen.
- `compose.yaml` geeft iedere instelling uit `.env` door aan de container. Daarvoor is Docker Compose 2.24 of nieuwer nodig.
- Vitest 5.0.5 en Zod 4.6.7, vanwege bekende kwetsbaarheden in de oudere versies.

- In productie is ook het API-schema (`/api/openapi.json`) niet meer bereikbaar.
- De basisimages staan vast op een digest. Een registry-mirror stel je in bij de Docker-daemon in plaats van met build-argumenten.

### Verwijderd

- De oude implementatie in `archive/oak-v1/`, Hermes-Oak, de orchestratiebestanden en de vervangen ADR's staan niet meer in de repository (ADR-0023). Het besluitenregister staat nu in `docs/DECISIONS.md`.

### Opgelost

- Bij een Purified Pokémon telde OAK voor een evolutie de gewone candykosten, ook als de Game Master lagere kosten noemt.
- Een bevestiging op de actielijst gold voor alle regel- en tagbescherming samen. Een later toegevoegde beschermende tag of regel viel er daardoor ook onder. Een bevestiging geldt nu per concrete reden en tag. Bestaande bevestigingen voor regelbescherming moet je één keer opnieuw geven.
- Het privacyfilter liet geneste waarden in gevechtsstatistieken, badges, valuta en items ongemoeid. Iedere bewaarde waarde gaat nu door hetzelfde filter, en eerder bewaarde exports filtert OAK bij de eerstvolgende start opnieuw.

- De knop *Test Connection* in PGSharp gaf een `400`. OAK beantwoordt een verbindingstest nu met `200`, zonder iets te importeren.
- Uploads controleren eerst de login en de maximale grootte, en lezen pas daarna het bestand.
- Een export met een onmogelijke datum of een fout in de verwerking blijft niet meer hangen, en een afgebroken gzip-bestand wordt geweigerd.
- Een mislukte login staat in het auditlog.
- Een GET-verzoek kan niet meer mislukken met *database is locked* als er tegelijk iets wordt opgeslagen.
- Ontbreekt het bestand van de actieve Game Data-versie, bijvoorbeeld na het terugzetten van alleen de database, dan bouwt OAK het opnieuw op.
- De planner negeerde het uitzetten van *Evoluties toestaan*.
- Een HTML-foutpagina van een proxy liet een upload eindeloos hangen.
- Dialoogvensters hebben een toegankelijke naam, houden de toetsenbordfocus vast en geven hem bij sluiten terug.
- Een Gigantamax-Pokémon kreeg in Max Battles het type van zijn snelle aanval. OAK gebruikt nu zijn G-Max-aanval uit de Game Data.

## [2.0.0] - nog niet uitgebracht

OAK 2.0 is een volledig nieuwe applicatie en vervangt de Calcy IV- en PostgreSQL-implementatie van OAK v1 (DEC-003).

### Toegevoegd

- Koppeling met PGSharp *Export Account Data* via een persoonlijke webhook of een upload van `PGSStats.json`, met dezelfde verwerking voor beide.
- Verliesvrije Pokémon- en tag-ID's als tekst, van database tot frontend.
- Importclassificatie: volledig, gedeeltelijk, ongeldig, verouderd of dubbel. Alleen een volledige import markeert Pokémon als niet meer in inventaris.
- Synchronisatiehistorie met een gebeurtenis per verschenen, gewijzigde, verdwenen of teruggekeerde Pokémon.
- Game Data van PokeMiners en PvPoke, met versiebeheer, controle vóór activering, terugrollen en installatie zonder internet.
- PvP-analyse voor Great, Ultra en Master League, movesetadvies, evolutie- en power-upplanner, Team Builder, raid-, Rocket- en Max Battle-overzichten.
- Cleanup Manager met harde bescherming, zachte bescherming voor favorieten, vintage-bescherming voor 2016–2019, een bruikbaarheidsscore en een bewaarscore (ADR-0019), dubbelen, een actielijst met bevestiging per Pokémon, een CSV-export en een printbare checklist.
- Nederlandstalige React-interface met standaard dark mode en een responsive opmaak.
- Meerdere gebruikers en traineraccounts, Argon2id, sessiecookies, CSRF, throttling en gehashte webhook-tokens.
- Docker-image met PUID/PGID, healthcheck en `compose.yaml`. CI met tests, end-to-end tests en een Docker-controle. Releases naar `ghcr.io/arjancool/oak-pogo` voor amd64 en arm64.
- Documentatie in `docs/` en deze changelog.
