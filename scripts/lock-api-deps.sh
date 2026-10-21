#!/usr/bin/env bash
# Regenerate the fully pinned, hash-locked API dependency files.
#
#   apps/api/requirements.lock      <- apps/api/requirements.txt      (runtime / Docker)
#   apps/api/requirements-dev.lock  <- apps/api/requirements-dev.txt  (CI / tests)
#
# requirements*.txt hold the human-edited version RANGES; the .lock files are
# generated and must never be edited by hand. Run this after changing a range
# or to pick up security fixes (pass e.g. `--upgrade-package pytest` or
# `--upgrade`; extra args go to pip-compile), then commit both .lock files.
#
# Uses pip-tools from $LOCK_COMPILER (default: pip-compile on PATH). Resolve on
# the same Python minor version as production (3.12) — wheels/markers differ.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCK_COMPILER="${LOCK_COMPILER:-pip-compile}"
export CUSTOM_COMPILE_COMMAND="./scripts/lock-api-deps.sh"
cd "$ROOT/apps/api"

common=(--quiet --generate-hashes --allow-unsafe --strip-extras --resolver=backtracking)
"$LOCK_COMPILER" "${common[@]}" "$@" -o requirements.lock requirements.txt
# The dev lock is constrained by the runtime lock so tests always run against
# exactly the versions shipped in the image.
"$LOCK_COMPILER" "${common[@]}" "$@" -c requirements.lock -o requirements-dev.lock requirements-dev.txt
echo "locked: $(grep -c '^[a-zA-Z]' requirements.lock) runtime, $(grep -c '^[a-zA-Z]' requirements-dev.lock) dev packages"
