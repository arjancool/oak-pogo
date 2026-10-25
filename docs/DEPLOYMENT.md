# Installatie en beheer

OAK draait als één container met de backend, de frontend en een SQLite-database in `/data`. Er is geen aparte database- of cacheserver nodig.

## Snel starten vanuit de broncode

```bash
git clone https://github.com/arjancool/oak-pogo.git
cd oak-pogo
cp .env.example .env        # pas minstens OAK_BASE_URL aan
docker compose up -d --build
```

Open daarna het adres uit `OAK_BASE_URL`. De eerste gebruiker die zich aanmeldt, wordt eigenaar. Koppel PGSharp via **Beheer → PGSharp Sync**.

## Kant-en-klare image

Iedere push naar `main` publiceert `ghcr.io/arjancool/oak-pogo:latest` en `ghcr.io/arjancool/oak-pogo:sha-<commit>`. Een tag `v2.1.0` publiceert ook `2.1.0` en `2.1`. De image is er voor amd64 en arm64.

Publiceren is de laatste stap van de CI-run voor die commit. Hij start pas als de backend-, frontend- en browsertests, de Docker-build, de beveiligingscontroles en de kwetsbaarheidsscan allemaal zijn geslaagd. Faalt er één, dan verschijnt er geen nieuwe image. Een handmatige run via **Actions → CI → Run workflow** doorloopt dezelfde controles en publiceert alleen vanaf `main` of een versietag. De controles draaien op amd64. De arm64-image wordt uit dezelfde commit gebouwd, maar niet apart getest.

Het pakket hoort bij een privé-repository en is daarom ook privé. Een server moet één keer inloggen met een GitHub-token dat alleen `read:packages` mag:

```bash
docker login ghcr.io -u <github-gebruikersnaam>
```

Wie geen login wil, kan het pakket openbaar maken in de pakketinstellingen op GitHub. De broncode blijft dan privé.

Een minimale compose-definitie:

```yaml
services:
  oak:
    image: ghcr.io/arjancool/oak-pogo:latest
    container_name: oak
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - /pad/naar/oak/data:/data
    environment:
      - TZ=Europe/Amsterdam
      - PUID=1000
      - PGID=1000
      - OAK_BASE_URL=https://oak.example.org
      - OAK_TRUSTED_PROXY_CIDRS=172.16.0.0/12
```

Bijwerken gaat met `docker compose pull && docker compose up -d`. Voor iedere databasemigratie maakt OAK zelf een back-up in `/data/backups`.

## Gebruiker en rechten

De container start als root, maakt de datamap eigendom van `PUID:PGID` en laat daarna alle rechten vallen. OAK zelf draait nooit als root. `PUID` of `PGID` 0 weigert de container. Wie de container liever direct als vaste gebruiker start (`user: "1000:1000"` in compose of `runAsUser` in Kubernetes), moet zelf zorgen dat die gebruiker in de datamap kan schrijven.

## Instellingen

Alle instellingen zijn omgevingsvariabelen. Waarden met een standaard hoef je niet op te geven.

Met de `compose.yaml` uit de repository zet je ze in `.env` naast dat bestand. Compose geeft iedere regel uit `.env` door aan de container (`env_file` met `required: false`, vanaf Docker Compose 2.24). `OAK_DATA_DIR` en `OAK_PORT` liggen daar vast, omdat het volume en de poortkoppeling ervan uitgaan.

Gebruik je een eigen compose-definitie, zoals het voorbeeld hierboven, dan bereikt een regel in `.env` de container alleen als je hem doorgeeft. Zet de variabele dan onder `environment`, of voeg `env_file` toe. Controleer na een wijziging wat de container echt krijgt:

```bash
docker compose config | grep OAK_
docker exec oak env | grep OAK_
```

| Variabele | Standaard | Betekenis |
|---|---|---|
| `OAK_BASE_URL` | `http://localhost:8080` | Het adres waarop je OAK opent. Bepaalt de webhook-URL en of cookies alleen via https gaan. Met `https://` stuurt OAK ook een HSTS-header. |
| `OAK_SECRET_KEY` | leeg | Sleutel voor sessies en vingerafdrukken, minimaal 32 tekens. Leeg betekent dat OAK eenmalig een sleutel maakt in `/data/.secret_key`. |
| `OAK_TRUSTED_PROXY_CIDRS` | leeg | Netwerken van reverse proxies, komma-gescheiden. Alleen hun `X-Forwarded-*`-headers worden vertrouwd. |
| `OAK_ALLOW_REGISTRATION` | `false` | Of nieuwe gebruikers zichzelf mogen registreren. De eigenaar kan altijd gebruikers toevoegen. |
| `OAK_TIMEZONE` | `Europe/Amsterdam` | Tijdzone voor vangstjaren en weergave. |
| `OAK_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` of `ERROR`. |
| `OAK_RAW_IMPORT_RETENTION_DAYS` | `14` | Dagen dat een ontvangen export bewaard blijft voor diagnose en opnieuw verwerken. 0 bewaart niets. |
| `OAK_MAX_IMPORT_MB` | `64` | Maximale grootte van een export. |
| `OAK_SESSION_IDLE_HOURS` | `168` | Een sessie verloopt na zoveel uur zonder gebruik. |
| `OAK_SESSION_MAX_DAYS` | `30` | Een sessie verloopt na zoveel dagen, ook bij gebruik. |
| `OAK_LOGIN_MAX_ATTEMPTS` | `10` | Mislukte inlogpogingen per venster voordat OAK tijdelijk blokkeert. |
| `OAK_LOGIN_WINDOW_MINUTES` | `15` | Lengte van dat venster. |
| `OAK_WEBHOOK_RATE_LIMIT_PER_HOUR` | `60` | Maximaal aantal webhookverzoeken per token per uur. |
| `OAK_GAMEDATA_AUTO_UPDATE` | `true` | Game Data automatisch bijwerken vanaf PokeMiners en PvPoke. |
| `OAK_GAMEDATA_UPDATE_INTERVAL_HOURS` | `24` | Hoe vaak OAK op nieuwe Game Data controleert. |
| `OAK_EVENTS_AUTO_UPDATE` | `true` | De eventkalender automatisch bijwerken vanaf LeekDuck.com via ScrapedDuck (ADR-0021). |
| `OAK_EVENTS_UPDATE_INTERVAL_HOURS` | `12` | Hoe vaak OAK de eventkalender ophaalt. |
| `OAK_EVENTS_URL` | ScrapedDuck `events.json` | Adres van de eventkalender, bijvoorbeeld voor een eigen spiegel. |
| `OAK_SPRITE_URL_TEMPLATE` | leeg | Beginwaarde voor een externe spritebron (ADR-0020). Beheer je normaal in de instellingen. |
| `OAK_PORT` | `8080` | Poort binnen de container. |
| `PUID`, `PGID` | `1000` | Eigenaar van de datamap en gebruiker waaronder OAK draait. |
| `TZ` | `Europe/Amsterdam` | Tijdzone van de container. |

## Reverse proxy

Zet OAK achter een reverse proxy met https. Stel `OAK_BASE_URL` in op het publieke adres en `OAK_TRUSTED_PROXY_CIDRS` op het netwerk waar de proxy vandaan komt. Zonder die laatste instelling ziet OAK ieder verzoek als afkomstig van de proxy, en delen alle gebruikers dan één limiet voor inlogpogingen.

De webhook-URL bevat een geheim token. OAK schrijft dat token nooit in zijn eigen logboek, maar de toegangslogs van je proxy doen dat standaard wel. Zet die logs uit voor `/api/v1/ingest/` of maskeer het pad.

Exports kunnen enkele megabytes groot zijn. Zorg dat de proxy verzoeken tot de ingestelde `OAK_MAX_IMPORT_MB` doorlaat.

### Nginx Proxy Manager

1. Maak een Proxy Host met als domein het adres uit `OAK_BASE_URL`.
2. Forward naar het IP-adres van de Docker-host en de gepubliceerde poort, bijvoorbeeld `8093`.
3. Zet onder SSL een certificaat aan, met **Force SSL** en **HTTP/2**.
4. Voeg onder **Advanced** toe:

```nginx
client_max_body_size 64m;
location /api/v1/ingest/ {
    access_log off;
    proxy_pass http://<docker-host>:8093;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Nginx Proxy Manager draait zelf in Docker. `OAK_TRUSTED_PROXY_CIDRS=172.16.0.0/12` dekt de standaard Docker-netwerken.

### Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name oak.example.org;
    # ssl_certificate ...;

    client_max_body_size 64m;

    location /api/v1/ingest/ {
        access_log off;
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Hier draait nginx op de host zelf: `OAK_TRUSTED_PROXY_CIDRS=127.0.0.1/32` en in compose `ports: ["127.0.0.1:8080:8080"]`.

### Caddy

```caddy
oak.example.org {
    request_body {
        max_size 64MB
    }
    log {
        output file /var/log/caddy/oak.log
        format filter {
            wrap json
            fields {
                request>uri regexp ^/api/v1/ingest/pgsharp/[^/?]+ /api/v1/ingest/pgsharp/[redacted]
            }
        }
    }
    reverse_proxy oak:8080
}
```

### Traefik

```yaml
services:
  oak:
    image: ghcr.io/arjancool/oak-pogo:latest
    environment:
      - OAK_BASE_URL=https://oak.example.org
      - OAK_TRUSTED_PROXY_CIDRS=172.16.0.0/12
    labels:
      - traefik.enable=true
      - traefik.http.routers.oak.rule=Host(`oak.example.org`)
      - traefik.http.routers.oak.entrypoints=websecure
      - traefik.http.routers.oak.tls.certresolver=letsencrypt
      - traefik.http.services.oak.loadbalancer.server.port=8080
```

Traefik schrijft het volledige pad in zijn toegangslog als dat aan staat. Gebruik dan `accessLog.fields.names.RequestPath=drop`, of zet het toegangslog uit.

## Gezondheid en status

- `GET /health/live` antwoordt zodra het proces draait.
- `GET /health/ready` antwoordt pas als de database bereikbaar is, en meldt of er Game Data actief is. De Docker-healthcheck gebruikt dit adres.
- **Beheer → Instellingen** toont voor de eigenaar versie, build, schijfruimte, achtergrondtaken en de herkomst van de geheime sleutel.

## Logboek

OAK schrijft JSON-regels naar stdout. Webhook-tokens, sessietokens, wachtwoorden en de inhoud van exports komen er nooit in. Iedere regel heeft een tijdstempel in UTC. Het voorbeeld in `compose.yaml` beperkt het logboek tot drie bestanden van 10 MB.

## Zelf bouwen via een registry-mirror

De basisimages staan in de Dockerfile vast op een versie en een digest. Dependabot houdt ze bij. Wil je ze via een registry-mirror ophalen, stel die dan in bij de Docker-daemon, in `/etc/docker/daemon.json`:

```json
{ "registry-mirrors": ["https://mirror.gcr.io"] }
```

Herstart daarna Docker. De digest blijft gelden, dus de mirror moet precies dezelfde image leveren.

Back-ups en herstel staan in `docs/BACKUP_RESTORE.md`.
