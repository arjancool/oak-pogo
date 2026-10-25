#!/bin/sh
# Start OAK (or another command, for example 'sh' for diagnosis). As root, the script makes the
# data directory writable for PUID:PGID and drops all privileges before the command starts, so
# nothing in the container runs as root. Started as another user (compose 'user:', Kubernetes
# runAsUser), it runs the command directly.
set -eu

DATA_DIR="${OAK_DATA_DIR:-/data}"

if [ "$#" -eq 0 ]; then
  set -- python -m app
fi

if [ "$(id -u)" = "0" ]; then
  PUID="${PUID:-1000}"
  PGID="${PGID:-1000}"
  if [ "$PUID" = "0" ] || [ "$PGID" = "0" ]; then
    echo "OAK draait niet als root. Kies een andere PUID en PGID." >&2
    exit 1
  fi
  mkdir -p "$DATA_DIR"
  if [ "$(stat -c %u:%g "$DATA_DIR")" != "$PUID:$PGID" ]; then
    chown -R "$PUID:$PGID" "$DATA_DIR"
  fi
  exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups --inh-caps=-all env HOME=/tmp "$@"
fi

exec "$@"
