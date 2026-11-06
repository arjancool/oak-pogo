# Changelog

Alle noemenswaardige wijzigingen in OAK. De opbouw volgt [Keep a Changelog](https://keepachangelog.com/nl/1.1.0/) en de versies volgen [Semantic Versioning](https://semver.org/lang/nl/).

## [Nog niet uitgebracht]

### Toegevoegd

- De detailpagina toont de herkomst van een Pokémon: uitgebroed uit een ei, gevangen in een raid of na een gevecht met Team GO Rocket. Alleen die drie zijn met een echte export gecontroleerd. Een andere waarde staat er als `onbekend`, met de code. `docs/PGSHARP_INTEGRATION.md` legt uit hoe iedere waarde is gecontroleerd.
- De pagina Game Data toont van wanneer de gegevens zijn: de Game Master en PvPoke van de actieve versie, en de nieuwste Game Master bij PokeMiners. OAK leest daarvoor `timestamp.txt` van PokeMiners. Het resultaat van de laatste controle blijft op de pagina staan, met *Je hebt de nieuwste versie* of *Er is een nieuwere versie*. Een onbekende datum staat er als `onbekend`, met de reden.
- De eigenaar ziet onder Instellingen, bij Systeem, naast de draaiende versie de nieuwste release van OAK op GitHub, met de datum en een link als er een nieuwere is. OAK bewaart het antwoord 12 uur. Met `OAK_RELEASE_CHECK=false` vraagt OAK niets aan GitHub. Is GitHub niet bereikbaar, dan staat er `onbekend` met de reden.

### Beveiliging

- Ieder verzoek mag hoogstens 1 MB groot zijn. Alleen de webhook en de twee uploads houden hun grens van `OAK_MAX_IMPORT_MB`. Pas de grens in je reverse proxy aan zoals in `docs/DEPLOYMENT.md`.
- Een export heeft grenzen aan zijn opbouw: hoogstens 25.000 Pokémon-records, 500.000 objecten en lijsten, 4 miljoen waarden, 32 niveaus en 1.000 velden per object. OAK leest, filtert en bewaart een export voordat het de database op slot zet, en hoogstens twee tegelijk.
- Een import bewaart per ernst hoogstens 500 meldingen. Een taak die drie keer is onderbroken, start niet opnieuw.
- De blokkade na mislukte inlogpogingen geldt per gebruikersnaam en adres. Vanaf een ander adres kan een gebruiker gewoon inloggen. Veel mislukte pogingen voor één naam vanaf verschillende adressen vertragen alleen. Pogingen die tegelijk binnenkomen, kunnen een grens niet meer passeren, en een IPv6-adres telt per /64-blok.
- `docs/DEPLOYMENT.md` raadt aan om in `OAK_TRUSTED_PROXY_CIDRS` alleen het adres van de proxy te zetten, niet de hele Docker-range.
- Inloggen, de setup en registreren hashen of controleren het wachtwoord buiten de schrijftransactie. Andere schrijvers hoeven daar niet meer op te wachten.
- De geheime sleutel in `/data/.secret_key` heeft vanaf het begin de rechten 600. Is het bestand leeg of te kort, dan start OAK niet en zegt waarom, in plaats van stil een nieuwe sleutel te maken. De datamap krijgt de rechten 700 en nieuwe bestanden `umask 077`.
- De opgeslagen kopie van een export bewaart van een Pokémon alleen de velden die OAK leest, en onbekende velden alleen als ze onschuldig zijn. Het privacyfilter herkent meer gevoelige veldnamen, ook met cijfers zoals `s2Id`. Bewaarde exports worden bij de volgende start opnieuw gefilterd.

- Wachtwoord wijzigen heeft een grens op foute pogingen, en iedere foute poging komt in het auditlogboek. Na een wijziging eindigen alle sessies, ook de huidige, en krijgt de browser een nieuwe sessie. Hoogstens vier Argon2-berekeningen draaien tegelijk.
- Een eigen spritebron moet een `https://`-adres met een gewone hostnaam zijn. Alleen de host en de poort komen in de Content-Security-Policy. Een ongeldige `OAK_SPRITE_URL_TEMPLATE` negeert OAK met een melding.
- Downloads van de Game Data en de eventkalender hebben een maximale grootte, gaan alleen over https en volgen een doorverwijzing alleen naar dezelfde host. Bij een dataset staat het adres waar de inhoud echt vandaan kwam.
- Een lege eventkalender laat de vorige events staan, met een melding. Eerder verdwenen dan alle events en de regels voor *even bewaren*.
- Een geldig webhook-token werkt ook vanaf een adres dat eerder veel ongeldige tokens stuurde. Alleen ongeldige tokens worden dan geweigerd.
- Handmatige uploads en nieuwe pogingen zijn begrensd op 30 per gebruiker per uur, en per traineraccount wacht hoogstens één handmatige import.
- De structuursamenvatting van een import houdt per lijst hoogstens 200 namen, en een sleutel die geen veldnaam is, staat er als `*`.
- Geldige maar onverwachte JSON, zoals tekst met een losse surrogate of `NaN`, geeft een geweigerde import in plaats van een fout 500. Een onverwachte structuur in de Game Data of de eventkalender wordt een mislukte versie of update op de pagina.
- De volledige systeemstatus en de controle op nieuwe Game Data zijn alleen voor de eigenaar. De versie van OAK is pas na het inloggen te zien.
- Paginanummers, id's, voorkeuren, volledigheidsinstellingen en teamleden hebben een type en een grens. Een te groot getal of een onbekend veld geeft 422 in plaats van een fout 500 of opslag zonder grens.
- De images van BuildKit en QEMU in CI staan op een digest. Dependabot stelt een nieuwe versie pas een week na verschijnen voor.
- Kleine verbeteringen uit de audit: beveiligingsheaders ook bij een fout 500, uitloggen wist altijd de cookies, inloggen beëindigt een oude sessie van dezelfde browser, het verwijderen van een back-up komt in het auditlogboek, alleen https-links bij cups, een vaste controle op bestandsnamen van Game Data en back-ups, geen waarden van databasefouten in het logboek, geen verwerking meer voor een uitgeschakelde gebruiker, en een entrypoint die alleen numerieke PUID en PGID accepteert en zonder enige capability start.

### Gewijzigd

- *Controleren op updates* op de pagina Game Data is een POST geworden, omdat OAK het resultaat nu bewaart. De verzoeken naar buiten lopen buiten iedere transactie.
- Engels heet in de taalkeuze gewoon *English*, zonder *(beta)*. Bij een eerste bezoek zonder gekozen taal volgt OAK de taal van de browser.
- De actielijst vraagt een bevestiging voor een Pokémon die volgens het advies bewaard moet worden, en voor het beste exemplaar van een soort als alle exemplaren op de lijst staan. Zonder bevestiging staat hij niet in de zoekteksten.
- Het filter op dubbelen (`dup`) is bij een grote collectie veel sneller. Dezelfde zoekterm twee keer telt als één.
- De actielijst bundelt de zoekteksten voor Pokémon GO tot hoogstens 10 Pokémon per zoektekst, ook van verschillende soorten. OAK rekent iedere bundel na tegen de hele collectie. Zou een bundel ook een Pokémon vinden die niet op de lijst staat, dan krijgt de Pokémon die dat veroorzaakt een andere zoektekst.

### Opgelost

- Een bevestigde favoriet op de actielijst was met de zoektekst niet te vinden, omdat die altijd `!favorite` bevatte. Een zoektekst laat nu de veiligheidstermen weg die een Pokémon van de bundel zelf zouden verbergen, zoals `!favorite` of `!shadow`.
- Het opruimen van bewaarde exports kon een bestand verwijderen dat een nieuwe poging nog nodig had. De bewaartermijn telt nu vanaf de nieuwste import die het bestand gebruikt.
- Een Pokémon met een vorm die de Game Master als kostuum markeert, zoals een Pikachu met een eventhoed, telt nu als kostuum. Dat gold eerder alleen als PGSharp het kostuumveld vulde, en dat doet PGSharp niet altijd. Zo'n Pokémon krijgt nu de kostuumbescherming, de kostuumpunten in de bewaarscore, het label en de plek in het filter en de telling van kostuums. Migratie 0008 voegt daarvoor een afgeleide kolom toe.

## [2.0.0] - 2026-10-27

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
- Cleanup Manager met harde bescherming, zachte bescherming voor favorieten, vintage-bescherming voor 2016–2019, een bruikbaarheidsscore en een bewaarscore (ADR-0019) en dubbelen. Een actielijst met bevestiging per Pokémon en per beschermingsreden, zoekteksten voor in het spel, een CSV-export en een printbare checklist. XXL en XXS krijgen extra punten in de bewaarscore. In het tabblad Dubbelen zet je de transfer-kandidaten van een soort met één knop op de actielijst.
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
