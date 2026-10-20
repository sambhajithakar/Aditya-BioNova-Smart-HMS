#!/usr/bin/env bash
# Automated backup -> restore drill (synthetic data only). Exits non-zero on
# ANY mismatch. Used locally and by CI (job "backup-restore-drill").
#
#   1. create scratch DB, `alembic upgrade head` (owner role)
#   2. seed synthetic tenants/patients THROUGH THE API as hms_app (RLS on)
#   3. scripts/backup.sh  (gpg-encrypted with a throwaway passphrase)
#   4. negative checks: tampered dump is rejected; restore over a non-empty
#      DB without --force is refused
#   5. scripts/restore.sh into a second DB
#   6. compare fingerprints: row counts of EVERY table, RLS flags, policies,
#      triggers, functions, grants, default privileges, indexes, constraints,
#      sequences, alembic revision
#   7. functional checks on the restored DB: RLS hides rows without tenant
#      context; audit log append-only trigger fires; owner login works via API
#
# Env: PGHOST/PGPORT/PGUSER(owner, superuser locally)/PGPASSWORD, PG_BIN,
#      HMS_APP_PASSWORD (hms_app role), PYTHON (with API deps installed),
#      DRILL_SRC_DB / DRILL_DST_DB (must start with "hms_drill"), DRILL_KEEP=1
set -euo pipefail
set +x
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PGHOST="${PGHOST:-127.0.0.1}" PGPORT="${PGPORT:-5433}" PGUSER="${PGUSER:-hms}"
[[ -n "${PG_BIN:-}" ]] && export PATH="$PG_BIN:$PATH"
PYTHON="${PYTHON:-python3}"
SRC="${DRILL_SRC_DB:-hms_drill_src}"
DST="${DRILL_DST_DB:-hms_drill_restored}"
APP_PW="${HMS_APP_PASSWORD:-change_me}"
for db in "$SRC" "$DST"; do
  [[ "$db" =~ ^hms_drill[A-Za-z0-9_]*$ ]] || { echo "drill: refusing DB name '$db' (must start with hms_drill)" >&2; exit 2; }
done

WORK="$(mktemp -d)"; chmod 700 "$WORK"
cleanup() {
  rm -rf "$WORK"
  if [[ "${DRILL_KEEP:-0}" != "1" ]]; then
    for db in "$SRC" "$DST"; do psql -X -q -d postgres -c "DROP DATABASE IF EXISTS \"$db\" WITH (FORCE)" >/dev/null 2>&1 || true; done
  fi
}
trap cleanup EXIT
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DRILL FAILED: $*" >&2; exit 1; }
psqlq() { psql -X -q -v ON_ERROR_STOP=1 "$@"; }

step "1. scratch database $SRC + migrations"
for db in "$SRC" "$DST"; do psqlq -d postgres -c "DROP DATABASE IF EXISTS \"$db\" WITH (FORCE)"; done
psqlq -d postgres -c "CREATE DATABASE \"$SRC\" OWNER \"$PGUSER\""
(
  cd "$ROOT/apps/api"
  MIGRATION_DATABASE_URL="postgresql+psycopg2://$PGUSER@$PGHOST:$PGPORT/$SRC" \
    "$PYTHON" -m alembic upgrade head >"$WORK/alembic.log" 2>&1 || { cat "$WORK/alembic.log" >&2; exit 1; }
)
echo "migrated $SRC to revision $(psql -X -tA -d "$SRC" -c 'SELECT version_num FROM alembic_version')"

drill_api_env() {  # $1 = database
  export DATABASE_URL="postgresql+psycopg2://hms_app:$APP_PW@$PGHOST:$PGPORT/$1"
  export MIGRATION_DATABASE_URL="postgresql+psycopg2://$PGUSER@$PGHOST:$PGPORT/$1"
  JWT_SECRET="drill-only-$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  export JWT_SECRET
  export ENVIRONMENT=test
  export PYTHONWARNINGS=ignore::DeprecationWarning
}

step "2. synthetic data through the API (hms_app, RLS enforced)"
( cd "$ROOT/apps/api" && drill_api_env "$SRC" && "$PYTHON" "$ROOT/scripts/drill_seed.py" seed )

step "3. backup (encrypted, checksummed)"
BACKUP_PASSPHRASE="$(head -c 32 /dev/urandom | base64)"
export BACKUP_PASSPHRASE
PGDATABASE="$SRC" BACKUP_DIR="$WORK/backups" BACKUP_RETENTION_DAYS=7 \
  BACKUP_RESULT_FILE="$WORK/result" "$ROOT/scripts/backup.sh"
DUMP="$(cat "$WORK/result")"

step "4. negative checks"
cp "$DUMP" "$WORK/tampered.dump.gpg"; cp "$DUMP.sha256" "$WORK/tampered.dump.gpg.sha256"
sed -i "s#$(basename "$DUMP")#tampered.dump.gpg#" "$WORK/tampered.dump.gpg.sha256"
printf '\x00' | dd of="$WORK/tampered.dump.gpg" bs=1 seek=100 conv=notrunc status=none
if "$ROOT/scripts/restore.sh" "$WORK/tampered.dump.gpg" "$DST" 2>"$WORK/err"; then
  fail "tampered backup was restored"
fi
grep -q "CHECKSUM MISMATCH" "$WORK/err" || fail "tampered backup rejected for the wrong reason: $(cat "$WORK/err")"
echo "ok: tampered dump rejected (checksum mismatch)"
if "$ROOT/scripts/restore.sh" "$DUMP" "$SRC" 2>"$WORK/err"; then
  fail "restore over a non-empty database without --force succeeded"
fi
grep -q "not empty" "$WORK/err" || fail "non-empty refusal missing: $(cat "$WORK/err")"
echo "ok: restore into non-empty '$SRC' refused without --force"

step "5. restore into $DST"
"$ROOT/scripts/restore.sh" "$DUMP" "$DST"

step "6. compare source vs restored"
psql -X -v ON_ERROR_STOP=1 -d "$SRC" -f "$ROOT/scripts/drill_fingerprint.sql" > "$WORK/src.fp"
psql -X -v ON_ERROR_STOP=1 -d "$DST" -f "$ROOT/scripts/drill_fingerprint.sql" > "$WORK/dst.fp"
section_count() { awk -v s="## $2" '/^## /{on=($0==s); next} on' "$1" | grep -c . || true; }
rows_total() { awk '/^## /{on=($0=="## row_counts"); next} on' "$1" | awk -F'|' '{s+=$2} END{print s+0}'; }
printf '%-20s %8s %8s\n' "section" "source" "restored"
for s in row_counts rls_enabled policies triggers functions table_grants default_privileges indexes constraints sequences alembic_version; do
  printf '%-20s %8s %8s\n' "$s" "$(section_count "$WORK/src.fp" "$s")" "$(section_count "$WORK/dst.fp" "$s")"
done
printf '%-20s %8s %8s\n' "total rows" "$(rows_total "$WORK/src.fp")" "$(rows_total "$WORK/dst.fp")"
if ! diff -u "$WORK/src.fp" "$WORK/dst.fp" > "$WORK/fp.diff"; then
  head -50 "$WORK/fp.diff" >&2
  fail "source and restored databases differ"
fi
(( $(section_count "$WORK/dst.fp" policies) > 0 )) || fail "no RLS policies after restore"
(( $(section_count "$WORK/dst.fp" triggers) > 0 )) || fail "no triggers after restore"
(( $(rows_total "$WORK/dst.fp") > 0 )) || fail "restored database has no rows"
echo "ok: fingerprints identical (every table's row count, RLS, policies, triggers, grants, ...)"

step "7. functional checks on $DST"
n="$(PGPASSWORD="$APP_PW" psql -X -tA -v ON_ERROR_STOP=1 -U hms_app -d "$DST" -c "SELECT count(*) FROM patients")"
[[ "$n" == "0" ]] || fail "hms_app sees $n patients without tenant context (RLS broken)"
echo "ok: RLS — hms_app sees 0 patients without tenant context"
if psql -X -q -v ON_ERROR_STOP=1 -d "$DST" \
     -c "UPDATE audit_events SET id = id WHERE ctid = (SELECT ctid FROM audit_events LIMIT 1)" 2>"$WORK/err"; then
  fail "audit_events UPDATE succeeded after restore (append-only trigger missing)"
fi
grep -q "append-only" "$WORK/err" || fail "audit UPDATE failed for an unexpected reason: $(cat "$WORK/err")"
echo "ok: audit_events append-only trigger rejects UPDATE"
( cd "$ROOT/apps/api" && drill_api_env "$DST" && "$PYTHON" "$ROOT/scripts/drill_seed.py" login )

printf '\nDRILL PASSED: %s -> %s (%s)\n' "$SRC" "$DST" "$(basename "$DUMP")"
