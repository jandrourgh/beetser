#!/bin/sh
set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

if [ "$(id -u)" = "0" ]; then
    if [ "$PUID" != "1000" ] || [ "$PGID" != "1000" ]; then
        groupmod -o -g "$PGID" beetser 2>/dev/null || true
        usermod -o -u "$PUID" beetser 2>/dev/null || true
    fi

    mkdir -p "${BEETSER_DATA_DIR:-/config}"
    chown -R "$PUID:$PGID" "${BEETSER_DATA_DIR:-/config}" 2>/dev/null || true

    exec gosu "$PUID:$PGID" "$@"
fi

exec "$@"
