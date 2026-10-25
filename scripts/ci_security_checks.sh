#!/usr/bin/env bash
# Security checks against a running OAK container, run by CI after the Docker build.
#
#   scripts/ci_security_checks.sh <container> <image> <base-url>
#
# The container must run in production mode without OAK_SECRET_KEY, as in CI. With OAK_PLATFORM
# (for example linux/arm64) the extra containers it starts use that platform.
set -euo pipefail

container="$1"
image="$2"
base="$3"

fail() {
  echo "FOUT: $*" >&2
  exit 1
}

# Security headers on the web interface and no caching of API responses.
headers=$(curl -fsS -D - -o /dev/null "$base/" | tr -d '\r' | tr '[:upper:]' '[:lower:]')
for expected in \
  "content-security-policy: default-src 'self'" \
  "x-content-type-options: nosniff" \
  "x-frame-options: deny" \
  "referrer-policy: no-referrer" \
  "cross-origin-opener-policy: same-origin"; do
  grep -qF "$expected" <<<"$headers" || fail "header ontbreekt: $expected"
done
api_headers=$(curl -sS -D - -o /dev/null "$base/api/v1/auth/me" | tr -d '\r' | tr '[:upper:]' '[:lower:]')
grep -qF "cache-control: no-store" <<<"$api_headers" || fail "API-antwoord zonder Cache-Control: no-store"
echo "Beveiligingsheaders aanwezig."

# No API documentation or schema in production.
for path in /api/docs /api/redoc /api/openapi.json; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$base$path")
  [ "$code" = "404" ] || fail "$path geeft $code in productie, verwacht 404"
done
echo "Geen API-documentatie of schema in productie."

# A webhook token never ends up in the log, while the request itself is logged.
secret="ci$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$base/api/v1/ingest/pgsharp/oakwh_AAAAAAAAAA_$secret" -d '{}')
[ "$code" = "404" ] || fail "onbekend webhook-token geeft $code, verwacht 404"
sleep 1
logs=$(docker logs "$container" 2>&1)
grep -qF '"path": "/api/v1/ingest/pgsharp/[redacted]"' <<<"$logs" || fail "webhookverzoek staat niet gemaskeerd in het logboek"
if grep -qF "$secret" <<<"$logs"; then
  fail "webhook-token staat in het logboek"
fi
echo "Webhook-token blijft uit het logboek."

# OAK runs as an ordinary user and keeps its generated secret key to itself.
[ "$(docker exec "$container" stat -c %u /proc/1)" != "0" ] || fail "OAK draait als root"
[ "$(docker exec "$container" stat -c %a /data/.secret_key)" = "600" ] || fail "/data/.secret_key heeft niet de rechten 600"
echo "OAK draait niet als root en de geheime sleutel heeft de rechten 600."

# The image refuses to run OAK as root, also when asked to.
for variable in PUID PGID; do
  set +e
  output=$(timeout 120 docker run --rm ${OAK_PLATFORM:+--platform "$OAK_PLATFORM"} -e "$variable=0" "$image" 2>&1)
  status=$?
  set -e
  [ "$status" -ne 0 ] && [ "$status" -ne 124 ] || fail "$variable=0 werd niet geweigerd (exitcode $status)"
  grep -qF "niet als root" <<<"$output" || fail "$variable=0 gaf geen duidelijke melding"
done
echo "PUID=0 en PGID=0 worden geweigerd."
