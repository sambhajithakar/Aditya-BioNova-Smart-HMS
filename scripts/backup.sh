#!/usr/bin/env bash
# Logical backup of one HMS database (pg_dump custom format), with optional
# encryption, a sha256 checksum file and retention pruning.
#
# Usage:  scripts/backup.sh                # uses the env vars below
#
# Connection (libpq env; the password is NEVER printed or put on argv):
#   PGHOST (127.0.0.1)  PGPORT (5433)  PGUSER (hms — the table-OWNER role)
#   PGDATABASE (hms_dev)  PGPASSWORD or ~/.pgpass
# Output:
#   BACKUP_DIR             directory for dumps (./backups), created 0700
#   BACKUP_RETENTION_DAYS  delete this DB's dumps older than N days (14; 0 = keep all)
# Encryption (pick at most one; strongly recommended outside local dev):
#   BACKUP_AGE_RECIPIENT   age public key (age1...) or path to a recipients file
#   BACKUP_PASSPHRASE      symmetric passphrase -> gpg --symmetric AES256
#                          (passed on a file descriptor, never on argv)
# Tools: PG_BIN (dir holding pg_dump; default: from PATH)
# Automation: BACKUP_RESULT_FILE — if set, the dump's path is written there.
#
# Produces  <BACKUP_DIR>/<db>_<UTC-timestamp>.dump[.age|.gpg]  + .sha256
# Roles are cluster-global and NOT in the dump: the target cluster must have
# `hms` and `hms_app` (scripts/setup_local_db.sh / postgres-init) before restore.
set -euo pipefail
set +x  # never trace: environment may hold secrets
umask 077

PGHOST="${PGHOST:-127.0.0.1}"; PGPORT="${PGPORT:-5433}"
PGUSER="${PGUSER:-hms}"; PGDATABASE="${PGDATABASE:-hms_dev}"
export PGHOST PGPORT PGUSER PGDATABASE
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION="${BACKUP_RETENTION_DAYS:-14}"
PG_DUMP="${PG_BIN:+$PG_BIN/}pg_dump"

die() { echo "backup: $*" >&2; exit 1; }
[[ "$PGDATABASE" =~ ^[A-Za-z0-9_]+$ ]] || die "invalid database name"
[[ "$RETENTION" =~ ^[0-9]+$ ]] || die "BACKUP_RETENTION_DAYS must be an integer"
if [[ -n "${BACKUP_AGE_RECIPIENT:-}" && -n "${BACKUP_PASSPHRASE:-}" ]]; then
  die "set only one of BACKUP_AGE_RECIPIENT / BACKUP_PASSPHRASE"
fi
command -v "$PG_DUMP" >/dev/null || die "pg_dump not found (set PG_BIN)"

mkdir -p "$BACKUP_DIR"; chmod 700 "$BACKUP_DIR"
ts="$(date -u +%Y%m%dT%H%M%SZ)"
base="${PGDATABASE}_${ts}.dump"
enc=""
if [[ -n "${BACKUP_AGE_RECIPIENT:-}" ]]; then
  command -v age >/dev/null || die "age not installed"
  enc="age"
elif [[ -n "${BACKUP_PASSPHRASE:-}" ]]; then
  command -v gpg >/dev/null || die "gpg not installed"
  enc="gpg"
fi
out="$BACKUP_DIR/$base${enc:+.$enc}"
tmp="$out.partial"
trap 'rm -f "$tmp"' EXIT

# --no-password: fail instead of prompting; -Fc: compressed, selective restore.
dump() { "$PG_DUMP" --no-password --format=custom --compress=6 --dbname="$PGDATABASE"; }
case "$enc" in
  age)
    if [[ -f "$BACKUP_AGE_RECIPIENT" ]]; then
      dump | age --encrypt -R "$BACKUP_AGE_RECIPIENT" -o "$tmp"
    else
      dump | age --encrypt -r "$BACKUP_AGE_RECIPIENT" -o "$tmp"
    fi ;;
  gpg)
    GNUPGHOME="$(mktemp -d)"; export GNUPGHOME
    trap 'rm -f "$tmp"; rm -rf "$GNUPGHOME"' EXIT
    dump | gpg --batch --quiet --yes --pinentry-mode loopback \
      --symmetric --cipher-algo AES256 --passphrase-fd 3 -o "$tmp" \
      3< <(printf '%s' "$BACKUP_PASSPHRASE") ;;
  *)
    dump > "$tmp" ;;
esac
[[ -s "$tmp" ]] || die "dump is empty"
mv "$tmp" "$out"
( cd "$BACKUP_DIR" && sha256sum "$(basename "$out")" > "$(basename "$out").sha256" )

size="$(du -h "$out" | cut -f1)"
echo "backup: wrote $out ($size, ${enc:-unencrypted})"
echo "backup: sha256 $(cut -d' ' -f1 "$out.sha256")"
# For automation (e.g. the restore drill): path of the file just written.
[[ -n "${BACKUP_RESULT_FILE:-}" ]] && printf '%s\n' "$out" > "$BACKUP_RESULT_FILE"
[[ -z "$enc" ]] && echo "backup: WARNING unencrypted dump — set BACKUP_AGE_RECIPIENT or BACKUP_PASSPHRASE outside local dev" >&2

if (( RETENTION > 0 )); then
  pruned=0
  while IFS= read -r -d '' old; do
    rm -f -- "$old" "$old.sha256"; pruned=$((pruned + 1))
  done < <(find "$BACKUP_DIR" -maxdepth 1 -type f \
             \( -name "${PGDATABASE}_*.dump" -o -name "${PGDATABASE}_*.dump.age" -o -name "${PGDATABASE}_*.dump.gpg" \) \
             -mtime +"$RETENTION" -print0)
  echo "backup: retention ${RETENTION}d — pruned $pruned old dump(s)"
fi
