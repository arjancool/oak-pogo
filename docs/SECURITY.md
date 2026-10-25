# Beveiliging

OAK is vaak via internet bereikbaar, omdat PGSharp de webhook vanaf je telefoon aanroept. Deze pagina beschrijft hoe OAK zich daartegen beschermt en wat je zelf moet regelen. Kwetsbaarheden meld je volgens `SECURITY.md` in de root van de repository.

## Wat OAK nooit doet

- OAK vraagt nooit om Pokémon GO-inloggegevens en logt nergens in.
- OAK stuurt niets naar het spel, automatiseert geen gameplay en zet nooit zelf een Pokémon over.
- OAK stuurt je collectie niet naar een externe dienst. Uitgaand verkeer is alleen het ophalen van openbare Game Data, en de spritebron als de eigenaar die aanzet.

## Inloggen en sessies

- **Wachtwoorden** worden gehasht met Argon2id, met de standaardparameters van argon2-cffi volgens RFC 9106. Een wachtwoord heeft minimaal 10 tekens.
- **Eerste gebruik:** er is geen standaardaccount en geen standaardwachtwoord. De eerste gebruiker maakt zelf het eigenaaraccount aan. Daarna is het setupscherm dicht.
- **Registratie** staat standaard uit (`OAK_ALLOW_REGISTRATION=false`). De eigenaar maakt gebruikers aan. Staat registratie aan, dan kan dat pas als de eigenaar bestaat. Zolang er geen eigenaar is, blijft het setupscherm beschikbaar.
- **Sessies** zijn een willekeurig token van 256 bits in een cookie met `HttpOnly` en `SameSite=Lax`. Als `OAK_BASE_URL` met `https://` begint, krijgt het cookie ook `Secure`. De database bewaart alleen de SHA-256-hash van het token. Er staat niets in `localStorage`.
- **Verlopen:** een sessie verloopt na 168 uur zonder gebruik en altijd na 30 dagen. Uitloggen trekt de sessie in. Een nieuw wachtwoord of het uitschakelen van een gebruiker trekt de andere sessies van die gebruiker in.
- **Wachtwoord opnieuw instellen:** de eigenaar kan voor een andere gebruiker een nieuw wachtwoord instellen. Alle sessies van die gebruiker eindigen dan meteen. Het auditlog vermeldt dat het wachtwoord opnieuw is ingesteld, nooit het wachtwoord zelf. Zijn eigen wachtwoord wijzigt ook de eigenaar alleen met zijn huidige wachtwoord, zodat een overgenomen sessie het eigenaaraccount niet kan overnemen.
- **CSRF:** ieder verzoek dat iets wijzigt, heeft de header `X-CSRF-Token` nodig. Die waarde is een HMAC van het sessietoken met de geheime sleutel. De frontend leest hem uit het cookie `oak_csrf`.
- **Throttling:** na 10 mislukte pogingen per gebruikersnaam of 30 per IP-adres in 15 minuten weigert OAK tijdelijk (instelbaar). OAK kijkt eerst naar het IP-adres, en een geweigerd verzoek legt niets vast. De administratie ruimt verlopen pogingen zelf op en houdt hoogstens 10.000 sleutels per limiet bij. Registratie heeft ook een limiet per IP-adres.

## Webhook

- Het token wordt gemaakt met `secrets` uit Python: een openbaar deel van 10 tekens om het record te vinden en een geheim deel van 256 bits.
- De database bewaart alleen de SHA-256-hash. De volledige URL zie je één keer, direct na het maken.
- OAK vergelijkt de hash in constante tijd.
- Per traineraccount is er hoogstens één actieve webhook. Een nieuwe URL maakt de oude direct ongeldig. Intrekken kan altijd.
- Een webhook werkt alleen zolang hij actief is en de gebruiker van het traineraccount actief is. OAK controleert dat voor het lezen van de export en opnieuw in de transactie die de import opslaat. Intrekken of uitschakelen stopt dus ook een upload die al bezig was. Wordt een uitgeschakelde gebruiker weer actief, dan werkt zijn bestaande webhook weer. Wil je dat niet, trek de webhook dan in.
- Per webhook zijn standaard 60 verzoeken per uur toegestaan. Na 20 verzoeken met een ongeldig token blokkeert OAK het IP-adres 10 minuten.
- Een verzoek mag na het uitpakken hoogstens `OAK_MAX_IMPORT_MB` (64 MB) groot zijn. Gecomprimeerde inhoud wordt begrensd uitgepakt, zodat een zip-bom geen geheugen opeet.
- Een upload via de interface wordt pas gelezen na de inlogcontrole, en nooit verder dan de limiet. Een te grote `Content-Length` wordt meteen geweigerd, en zonder die header stopt OAK zodra de limiet bereikt is.
- Het token staat in het pad van de URL, omdat PGSharp geen eigen headers kan meesturen. OAK schrijft het nooit in zijn logboek. Zorg dat je reverse proxy het ook niet logt: zie `docs/DEPLOYMENT.md`.
- Een export wordt nooit alleen op basis van de trainernaam aan een account gekoppeld. OAK gebruikt een HMAC-vingerafdruk van de spelers-ID uit de export.

## Scheiding tussen gebruikers

Iedere gebruiker ziet alleen de eigen traineraccounts (ADR-0016). Iedere query op accountgegevens filtert op traineraccount én gebruiker. Een Pokémon of account van een ander geeft 404, zodat zelfs het bestaan ervan niet uitlekt. `tests/test_auth.py` controleert dat gebruiker A niets van gebruiker B kan lezen of wijzigen.

De eigenaar beheert de installatie: gebruikers, Game Data, sprites, back-ups en het auditlogboek. De gegevens van andere gebruikers kan ook de eigenaar niet via de interface inzien.

## Verdere maatregelen

- **Headers:** iedere respons krijgt een Content-Security-Policy zonder inline scripts, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, een strenge `Permissions-Policy` en `Cross-Origin-Opener-Policy: same-origin`. Achter https komt daar HSTS bij. API-antwoorden krijgen `Cache-Control: no-store`.
- **CORS:** OAK zet geen CORS-headers. Een andere website kan dus niet namens je browser de API gebruiken.
- **Invoer:** Pydantic controleert iedere invoer. Zoektermen worden met parameters naar SQL vertaald, ook bij `LIKE`. React ontsnapt alle tekst. CSV-exports beschermen tegen formule-injectie in spreadsheets.
- **Logboek:** OAK schrijft geen request-bodies, wachtwoorden, sessietokens of webhook-tokens weg. Een filter maskeert tokens ook als ze per ongeluk in een melding terechtkomen. Het toegangslog van uvicorn staat uit.
- **Opgeslagen exports** zijn opgeschoond (zonder locaties, namen van andere spelers en interne spelers-ID's) en worden na 14 dagen verwijderd. Dat geldt ook voor een bestand dat geen export blijkt te zijn: een lijst of ander onverwacht formaat gaat door hetzelfde filter, en het exporttijdstip wordt alleen als tekst bewaard.
- **Geheime sleutel:** zonder `OAK_SECRET_KEY` maakt OAK eenmalig een sleutel van 48 willekeurige bytes in `/data/.secret_key`, met rechten 0600. De status meldt welke van de twee in gebruik is.
- **Productie:** `OAK_ENV` staat standaard op `production`. Dan zijn de interactieve API-documentatie en het API-schema (`/api/openapi.json`) uit.
- **Auditlogboek:** inloggen en mislukte inlogpogingen, wachtwoordwijzigingen, het aanmaken en verwijderen van accounts en webhooks, Game Data-wissels, instellingen en back-ups komen in `audit_log`.
- **Container:** OAK draait als gewone gebruiker, zonder capabilities en met `no-new-privileges`.
- **Afhankelijkheden:** alle Python- en npm-pakketten staan op een exacte versie, ook de indirecte. Voor Python legt `backend/uv.lock` iedere versie met controlesom vast. De Docker-build en CI installeren alleen wat daarin staat, en controleren iedere controlesom. De basisimages staan vast op een versie en een digest, de GitHub Actions op een commit-hash. Dependabot stelt iedere week updates voor. CI laat `npm audit` op alle npm-pakketten draaien, ook de ontwikkelgereedschappen, en faalt bij een melding met ernst hoog of kritiek. De release maakt een SBOM en een provenance-attestatie, en volgt pas als alle controles voor dezelfde commit zijn geslaagd. De releasejob bouwt de image één keer voor amd64 en arm64 en zet die zonder tag op ghcr.io. Daarna start hij precies die image per platform (arm64 via emulatie), voert dezelfde beveiligingscontroles en scan uit en geeft hem pas dan de tags. Wat je downloadt, is dus de geteste image.

## Controles in CI

Bij iedere push, iedere pull request en iedere maandagochtend bouwt CI de image, start de container en voert `scripts/ci_security_checks.sh` uit. Dat script controleert het volgende tegen de draaiende container.

- De beveiligingsheaders zijn aanwezig, en API-antwoorden hebben `Cache-Control: no-store`.
- `/api/docs`, `/api/redoc` en `/api/openapi.json` geven in productie een `404`.
- Een webhookverzoek staat in het logboek met `[redacted]` in plaats van het token.
- OAK draait niet als root, en `/data/.secret_key` heeft de rechten 600.
- De image weigert te starten met `PUID=0` of `PGID=0`.

Daarna scant [Grype](https://github.com/anchore/grype) de image op bekende kwetsbaarheden in de pakketten van het besturingssysteem en in de Python-afhankelijkheden. CI faalt bij een hoog of kritiek lek waarvoor een opgeloste versie bestaat. Grype staat vast op een digest. Trivy is bewust niet gekozen, omdat de toeleveringsketen daarvan in maart 2026 is gehackt (CVE-2026-33634). De scanner krijgt de image als archief en geen toegang tot de Docker-socket.

## Nog niet ingericht

- Dependabot-meldingen over kwetsbaarheden, Dependabot-beveiligingsupdates en secret scanning staan los van `.github/dependabot.yml`. De eigenaar zet ze aan in de repository-instellingen van GitHub, onder *Code security*, voor zover ze voor het account beschikbaar zijn.
- De image wordt niet ondertekend, bijvoorbeeld met cosign.
- De arm64-image start in CI onder emulatie, niet op echte arm64-hardware.
- Inloggen met een tweede factor of via OpenID Connect bestaat nog niet.
- Branchbescherming staat niet in de repository zelf. De eigenaar stelt in GitHub een ruleset in voor `main`: wijzigingen alleen via een pull request, de controles Backend, Frontend, End-to-end en Docker-build verplicht, en geen verwijderen of geforceerd overschrijven.

## Wat je zelf moet regelen

- Zet OAK achter https. Zonder https gaan wachtwoord en sessie onversleuteld over het netwerk.
- Maak het eigenaaraccount aan voordat OAK via internet bereikbaar is. Zolang er geen eigenaar is, kan de eerste bezoeker die aanmaken.
- Draait je reverse proxy op dezelfde machine, publiceer de poort dan alleen lokaal: `127.0.0.1:8080:8080` in plaats van `8080:8080`.
- Stel `OAK_TRUSTED_PROXY_CIDRS` in op het netwerk van je reverse proxy. Anders delen alle bezoekers één limiet voor inlogpogingen.
- Zet het toegangslog van je proxy uit voor `/api/v1/ingest/`, of maskeer het pad.
- Bewaar back-ups van `/data` op een veilige plek. Daarin staan je hele collectie en de geheime sleutel.
- Houd de image bij met `docker compose pull`.
