# Changelog

Alle noemenswaardige wijzigingen in OAK. De opbouw volgt [Keep a Changelog](https://keepachangelog.com/nl/1.1.0/) en de versies volgen [Semantic Versioning](https://semver.org/lang/nl/).

## [2.0.0] - nog niet uitgebracht

De eerste openbare versie van OAK.

### Toegevoegd

- Koppeling met PGSharp *Export Account Data* via een persoonlijke webhook of een upload van `PGSStats.json`, met dezelfde verwerking voor beide. Een upload kan worden geannuleerd en stopt na tien minuten.
- Verliesvrije Pokémon- en tag-ID's als tekst, van database tot frontend.
- Importclassificatie: volledig, gedeeltelijk, ongeldig, verouderd of dubbel. Een import vervangt de inventaris alleen als vaststaat dat de export bij het gekoppelde account hoort en wanneer hij is gemaakt. Alleen een volledige import markeert Pokémon als niet meer in inventaris. Een gedeeltelijke import kun je na controle als volledig bevestigen.
- Synchronisatiehistorie met een gebeurtenis per verschenen, gewijzigde, verdwenen of teruggekeerde Pokémon.
- Een privacyfilter dat locaties, namen van andere spelers en interne spelers-ID's op iedere diepte uit een export verwijdert.
- Game Data van PokeMiners en PvPoke, met versiebeheer, controle vóór activering, terugrollen en installatie zonder internet. Spelregels die daar niet in staan, zoals die voor purify, levert OAK zelf aan met bron (ADR-0022).
- Komende events uit de kalender van LeekDuck.com via ScrapedDuck (ADR-0021). Een transfer-kandidaat uit de evolutielijn van een Pokémon met een Community Day in de komende 14 dagen blijft bewaard tot na het event. Bij dubbele Transfer Candy krijg je een tip om te wachten. Per traineraccount kun je een event negeren of zelf een event toevoegen.
- PvP-analyse voor Great, Ultra en Master League, movesetadvies, een evolutie- en power-upplanner en een Team Builder. De league- en raidtabellen zijn te sorteren.
- Cups zoals de Fantasy Cup, met de regels en ranglijsten van PvPoke (ADR-0027). Per cup zie je welke Pokémon uit je collectie mee mogen, nu of na evolutie, en de Team Builder stelt er teams voor samen. Een Pokémon toont op zijn detailpagina in welke cups hij past.
- Raid-, Rocket- en Max Battle-overzichten en je beste gymverdedigers. De waarde als gymverdediger telt mee in het cleanupadvies, en de beste verdediger per soort blijft bewaard (ADR-0026). Een Pokémon die in een gym staat, stelt OAK niet voor als transfer. In de Cleanup Manager kun je filteren op de beste verdediger per soort en op Pokémon die nu in een gym staan.
- Een Pokédex: zoek iedere Pokémon uit de Game Data op naam of nummer. Je ziet zijn waarden, aanvallen, CP met 15/15/15, plaats in de leagues en als gymverdediger, hoeveel je er hebt en welke Pokémon uit je collectie ernaartoe kunnen evolueren, met candy, item en CP na evolutie.
- Op de detailpagina van een Shadow Pokémon rekenen met de Pokémon zoals hij is of zoals hij na purify wordt.
- Cleanup Manager met harde bescherming, zachte bescherming voor favorieten, vintage-bescherming voor 2016–2019, een bruikbaarheidsscore en een bewaarscore (ADR-0019) en dubbelen. Een actielijst met bevestiging per Pokémon en per beschermingsreden, zoekteksten voor in het spel, een CSV-export en een printbare checklist. XXL en XXS krijgen extra punten in de bewaarscore en een waarschuwing, ook op de actielijst.
- React-interface met standaard dark mode en een responsive opmaak. Nederlands is de standaardtaal. De interface is ook in het Engels beschikbaar. Die kies je rechtsboven of op de inlogpagina (ADR-0025). Ook de uitleg en meldingen die de server maakt, zoals de redenen in het cleanupadvies en foutmeldingen, verschijnen in de gekozen taal. De CSV-export, de printbare checklist en een paar itemnamen zijn nog Nederlands.
- Meerdere gebruikers en traineraccounts. De eigenaar maakt gebruikers aan en kan een wachtwoord opnieuw instellen. Argon2id, sessiecookies, CSRF, throttling, gehashte webhook-tokens en een auditlog.
- Docker-image met PUID/PGID, healthcheck en `compose.yaml`, voor Docker Compose 2.24 of nieuwer. De basisimages staan vast op een digest.
- CI met tests, end-to-endtests, een Docker-controle, beveiligingscontroles tegen de draaiende container, een kwetsbaarheidsscan met Grype en `npm audit`. De image wordt alleen gepubliceerd naar `ghcr.io/arjancool/oak-pogo`, voor amd64 en arm64, als alle controles slagen. Dependabot stelt iedere week updates voor.
- Documentatie in `docs/` en deze changelog.

### Beveiliging

Herstel na de audit van 25 oktober 2026:

- Een vangstdatum die bij een latere import verandert, past nu ook het vangstjaar aan. De transferlijst kijkt bovendien naar de actuele vangstdatum, zodat een Pokémon uit 2016–2019 nooit zonder bevestiging op de lijst komt. OAK berekent de afgeleide gegevens van alle Pokémon een keer opnieuw.
- De limiet op inlogpogingen houdt zijn geheugengebruik begrensd. Een geweigerd verzoek legt niets meer vast.
- Het privacyfilter werkt ook voor een bestand dat geen export blijkt te zijn, en bewaart het exporttijdstip alleen als tekst. Eerder opgeslagen exports filtert OAK opnieuw.
- Een webhook stopt zodra de gebruiker wordt uitgeschakeld of de webhook wordt ingetrokken, ook als de upload al bezig was.
- Een analyse mislukt niet meer als tegelijk iets anders wordt opgeslagen.
- Alle Python-pakketten, ook de indirecte, staan met controlesom in `backend/uv.lock`. De releasejob publiceert precies de image die hij per platform heeft getest.
- `tzdata` hoort bij de installatie, zodat OAK ook op Windows de tijdzones kent.
- Een back-up sluit zijn databaseverbindingen.
