#!/bin/sh
# Start OAK (or another command, for example 'sh' for diagnosis). As root, the script makes the
# data directory writable for PUID:PGID and drops all privileges before the command starts, so
# nothing in the container runs as root. Started as another user (compose 'user:', Kubernetes
# runAsUser), it runs the command directly.
set -eu
# Files OAK makes, such as the database, back-ups and imports, are for OAK alone.
umask 077

DATA_DIR="${OAK_DATA_DIR:-/data}"

if [ "$#" -eq 0 ]; then
  set -- python -m app
fi

# A user or group id: digits only, without leading zeros, so "00" or "+0" cannot pass as root.
numeric_id() {
  case "$2" in
    '' | *[!0-9]*)
      echo "$1 moet een getal zijn, bijvoorbeeld 1000." >&2
      exit 1
      ;;
  esac
  value=$(printf '%s' "$2" | sed 's/^0*//')
  printf '%s' "${value:-0}"
}

if [ "$(id -u)" = "0" ]; then
  PUID=$(numeric_id PUID "${PUID:-1000}")
  PGID=$(numeric_id PGID "${PGID:-1000}")
  if [ "$PUID" = "0" ] || [ "$PGID" = "0" ]; then
    echo "OAK draait niet als root. Kies een andere PUID en PGID." >&2
    exit 1
  fi
  mkdir -p "$DATA_DIR"
  if [ "$(stat -c %u:%g "$DATA_DIR")" != "$PUID:$PGID" ]; then
    chown -R "$PUID:$PGID" "$DATA_DIR"
  fi
  chmod 700 "$DATA_DIR"
  # No capabilities left, and none to gain again later through a setuid program.
  exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups --inh-caps=-all --bounding-set=-all \
    --no-new-privs env HOME=/tmp "$@"
fi

exec "$@"
