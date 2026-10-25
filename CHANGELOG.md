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
- Raid-, Rocket- en Max Battle-overzichten en je beste gymverdedigers.
- Op de detailpagina van een Shadow Pokémon rekenen met de Pokémon zoals hij is of zoals hij na purify wordt.
- Cleanup Manager met harde bescherming, zachte bescherming voor favorieten, vintage-bescherming voor 2016–2019, een bruikbaarheidsscore en een bewaarscore (ADR-0019) en dubbelen. Een actielijst met bevestiging per Pokémon en per beschermingsreden, zoekteksten voor in het spel, een CSV-export en een printbare checklist.
- Nederlandstalige React-interface met standaard dark mode en een responsive opmaak.
- Meerdere gebruikers en traineraccounts. De eigenaar maakt gebruikers aan en kan een wachtwoord opnieuw instellen. Argon2id, sessiecookies, CSRF, throttling, gehashte webhook-tokens en een auditlog.
- Docker-image met PUID/PGID, healthcheck en `compose.yaml`, voor Docker Compose 2.24 of nieuwer. De basisimages staan vast op een digest.
- CI met tests, end-to-endtests, een Docker-controle, beveiligingscontroles tegen de draaiende container, een kwetsbaarheidsscan met Grype en `npm audit`. De image wordt alleen gepubliceerd naar `ghcr.io/arjancool/oak-pogo`, voor amd64 en arm64, als alle controles slagen. Dependabot stelt iedere week updates voor.
- Documentatie in `docs/` en deze changelog.
