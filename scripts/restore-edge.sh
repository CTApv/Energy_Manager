#!/usr/bin/env sh
set -eu

if [ "$#" -ne 2 ] || [ "$1" != "--confirm" ]; then
  echo "Uso: $0 --confirm data/backups/energy-manager-edge-YYYYMMDDTHHMMSSZ.db" >&2
  exit 2
fi

backup="$2"
case "$backup" in
  data/backups/energy-manager-edge-*.db) ;;
  *) echo "Il backup deve trovarsi in data/backups e rispettare il nome previsto." >&2; exit 2 ;;
esac
[ -f "$backup" ] || { echo "Backup non trovato: $backup" >&2; exit 2; }

docker run --rm -v "$(pwd)/data:/work" python:3.13-alpine python - "$backup" <<'PY'
import sqlite3, sys
path = "/work/" + sys.argv[1].removeprefix("data/")
with sqlite3.connect(path) as db:
    result = db.execute("PRAGMA integrity_check").fetchone()[0]
if result != "ok":
    raise SystemExit(f"Backup non integro: {result}")
PY

docker compose -f docker-compose.edge.yml stop edge-api
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
if [ -f data/customer-edge.db ]; then cp -p data/customer-edge.db "data/customer-edge.db.before-restore-$stamp"; fi
cp -p "$backup" data/customer-edge.db
rm -f data/customer-edge.db-wal data/customer-edge.db-shm
docker compose -f docker-compose.edge.yml up -d edge-api edge-web gateway
echo "Ripristino completato. Copia precedente: data/customer-edge.db.before-restore-$stamp"
