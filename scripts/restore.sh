#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh into a target database.
#
# Usage:  scripts/restore.sh [--force] <backup-file> <target-db>
#
#   1. verifies <backup-file>.sha256 (mandatory — refuses without it);
#   2. decrypts .age (BACKUP_AGE_IDENTITY = identity file) or .gpg
#      (BACKUP_PASSPHRASE, passed on a file descriptor) on the fly;
#   3. checks the archive is a readable pg_dump custom-format file;
#   4. creates <target-db> if missing. If it exists and contains any table,
#      it REFUSES unless --force, which drops and recreates it (terminating
#      connections). Never point --force at a live database you need.
#   5. pg_restore --exit-on-error --single-transaction, keeping owners and
#      grants (roles `hms`/`hms_app` must already exist in the cluster).
#
# Connection: libpq env (PGHOST/PGPORT/PGUSER/PGPASSWORD or ~/.pgpass); the
# role needs CREATEDB and must own (or be superuser over) the restored objects.
# Tools: PG_BIN (dir holding pg_restore/psql; default: from PATH)
set -euo pipefail
set +x
umask 077

PGHOST="${PGHOST:-127.0.0.1}"; PGPORT="${PGPORT:-5433}"; PGUSER="${PGUSER:-hms}"
export PGHOST PGPORT PGUSER
P="${PG_BIN:+$PG_BIN/}"
die() { echo "restore: $*" >&2; exit 1; }

force=0
args=()
for a in "$@"; do
  case "$a" in
    --force) force=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    -*) die "unknown option $a" ;;
    *) args+=("$a") ;;
  esac
done
(( ${#args[@]} == 2 )) || die "usage: restore.sh [--force] <backup-file> <target-db>"
file="${args[0]}"; target="${args[1]}"
[[ "$target" =~ ^[A-Za-z0-9_]+$ ]] || die "invalid target database name"
[[ -f "$file" ]] || die "no such file: $file"
[[ -f "$file.sha256" ]] || die "checksum file $file.sha256 missing — refusing to restore"

# 1. checksum (the .sha256 holds the basename, so check from its directory)
( cd "$(dirname "$file")" && sha256sum --check --status "$(basename "$file").sha256" ) \
  || die "CHECKSUM MISMATCH for $file — refusing to restore"
echo "restore: checksum OK ($(cut -d' ' -f1 "$file.sha256"))"

# 2. decryption pipeline
case "$file" in
  *.age)
    [[ -n "${BACKUP_AGE_IDENTITY:-}" && -f "$BACKUP_AGE_IDENTITY" ]] \
      || die "set BACKUP_AGE_IDENTITY to the age identity (private key) file"
    stream() { age --decrypt -i "$BACKUP_AGE_IDENTITY" "$file"; } ;;
  *.gpg)
    [[ -n "${BACKUP_PASSPHRASE:-}" ]] || die "set BACKUP_PASSPHRASE to decrypt"
    GNUPGHOME="$(mktemp -d)"; export GNUPGHOME
    trap 'rm -rf "$GNUPGHOME"' EXIT
    stream() {
      gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 3 --decrypt "$file" \
        3< <(printf '%s' "$BACKUP_PASSPHRASE")
    } ;;
  *.dump) stream() { cat "$file"; } ;;
  *) die "unrecognised backup extension (expected .dump, .dump.age or .dump.gpg)" ;;
esac

# 3. archive sanity: must list as a pg_dump archive
toc_entries="$(stream | "${P}pg_restore" --list 2>/dev/null | grep -c -v '^;' || true)"
(( toc_entries > 0 )) || die "not a readable pg_dump custom archive (wrong key/passphrase?)"
echo "restore: archive OK ($toc_entries TOC entries)"

# 4. target database
psql_admin() { "${P}psql" --no-password -X -q -v ON_ERROR_STOP=1 -d postgres "$@"; }
exists="$(psql_admin -tAc "SELECT 1 FROM pg_database WHERE datname = '$target'")"
if [[ "$exists" == "1" ]]; then
  ntables="$("${P}psql" --no-password -X -tA -d "$target" -c \
    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.relkind IN ('r','p') AND n.nspname NOT IN ('pg_catalog','information_schema')
       AND n.nspname NOT LIKE 'pg_toast%'")"
  if (( ntables > 0 )); then
    (( force == 1 )) || die "database '$target' is not empty ($ntables tables) — pass --force to drop and replace it"
    echo "restore: --force: dropping non-empty database '$target'"
    psql_admin -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$target' AND pid <> pg_backend_pid()" >/dev/null
    psql_admin -c "DROP DATABASE \"$target\""
    exists=""
  fi
fi
if [[ "$exists" != "1" ]]; then
  psql_admin -c "CREATE DATABASE \"$target\""
fi

# 5. restore (atomic: any error rolls the whole restore back)
stream | "${P}pg_restore" --no-password --exit-on-error --single-transaction -d "$target"
echo "restore: restored $(basename "$file") into '$target'"
