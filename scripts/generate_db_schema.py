#!/usr/bin/env python3
"""Generate DATABASE_SCHEMA.md from a freshly migrated PostgreSQL database.

The catalog of a database migrated with ``alembic upgrade head`` is the source
of truth; this script only reads it (pg_catalog / pg_policies) plus the
Alembic revision docstrings, and writes deterministic Markdown (sorted, no
timestamps, no row data except the seeded RBAC catalogue).

Usage (connect as the schema OWNER role so every object is visible):

    python scripts/generate_db_schema.py \\
        --dsn postgresql://hms:change_me@127.0.0.1:5433/hms_docs_gen

Requires psycopg2 (installed with the API dependencies).
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import re
import sys

import psycopg2

ROOT = pathlib.Path(__file__).resolve().parent.parent
VERSIONS = ROOT / "apps" / "api" / "alembic" / "versions"
OUT = ROOT / "DATABASE_SCHEMA.md"
APP_ROLE = "hms_app"
SCHEMA = "public"

HEADER = """\
# Database Schema (PostgreSQL 16)

> **Generated file.** Everything from the "Migrations" heading down is produced
> by `scripts/generate_db_schema.py` from the catalog of a freshly migrated
> database. The "Tenancy model" overview is maintained inside the generator.
> Do not edit by hand. To regenerate:
>
> ```bash
> # 1. empty database, migrated as the owner role
> psql -h 127.0.0.1 -p 5433 -U hms -d postgres \\
>   -c "DROP DATABASE IF EXISTS hms_docs_gen" -c "CREATE DATABASE hms_docs_gen OWNER hms"
> cd apps/api && \\
>   DATABASE_URL=postgresql+psycopg2://hms_app:<pw>@127.0.0.1:5433/hms_docs_gen \\
>   MIGRATION_DATABASE_URL=postgresql+psycopg2://hms:<pw>@127.0.0.1:5433/hms_docs_gen \\
>   JWT_SECRET=<48+ random chars> alembic upgrade head
> # 2. generate (as the OWNER role)
> cd ../.. && python scripts/generate_db_schema.py \\
>   --dsn postgresql://hms:<pw>@127.0.0.1:5433/hms_docs_gen
> ```
>
> CI does not check this file; regenerate it whenever a migration is added.

## Tenancy model (overview)

- **Shared database, shared schema, row-level tenancy.** Every tenant-owned
  table carries `organization_id` and has PostgreSQL row-level security (RLS)
  enabled. Policies compare it with the GUC `app.current_org_id`.
- **Tenant context comes only from the verified token.** For each request the
  API sets transaction-local GUCs with `set_config(name, value, true)`:
  `app.current_org_id` and `app.current_user_id` (plus `app.is_bootstrap`
  during organization registration). Transaction-local means a pooled
  connection never carries one tenant's context into another request. No
  client header or parameter can set them.
- **Two roles.** Migrations run as the table **owner** (`MIGRATION_DATABASE_URL`).
  The application runs as **`hms_app`**, a non-owner, non-superuser role
  without `BYPASSRLS`, so RLS is always enforced for it. RLS is not `FORCE`d,
  so the owner role (migrations, backups, this generator) sees all rows. The
  "Grants for hms_app" lines below are the complete privilege set of the app.
- **Tables without RLS by design:**
  - `users`, `auth_sessions`, `mfa_recovery_codes`, `password_reset_tokens`:
    identity-level data. A user can belong to several organizations, and
    login, refresh, MFA and password reset happen *before* any tenant context
    exists. Access is scoped by the service layer to the authenticated user;
    secrets are stored only as hashes (or encrypted, for TOTP seeds).
  - `rate_limit_counters`: keyed by a hash of IP / account, consulted before
    authentication; contains no tenant data.
  - `comms_messages`: the outbound message log (e-mail/SMS/WhatsApp) of the
    mock/suppressed providers; written from pre-tenant flows such as
    password reset. The app may insert and read, never update or delete.
  - Reference catalogues (`roles`, `permissions`, `role_permissions`,
    `drug_catalog`, `lab_test_catalog`) are global, read-only for `hms_app`.
- **Cross-tenant ids look like "not found".** Because RLS hides other tenants'
  rows, the API returns 404 for them.
- **Append-only ledgers and immutable clinical records are enforced in the
  database**, not just in code: `BEFORE UPDATE/DELETE` triggers raise on
  `audit_events`, `ledger_entries`, stock and inventory movements, payments,
  refunds, signed prescriptions, dispenses, released lab results, issued
  invoices and similar (see the per-table "Triggers" lists), and `hms_app`
  additionally lacks `UPDATE`/`DELETE` grants on several of them. Trigger
  errors (`P0001`) are surfaced by the API as `409`.
- **SECURITY DEFINER functions** are the only paths that cross the RLS
  boundary (audit inserts with NULL organization for pre-tenant security
  events; resolving the organization of a pending invitation token). They are
  listed at the end with their `search_path` pinning.
"""


def first_paragraph(doc: str | None) -> str:
    if not doc:
        return ""
    lines = []
    for line in doc.strip().splitlines():
        if not line.strip() or line.startswith("Revision ID"):
            break
        lines.append(line.strip())
    return " ".join(lines)


def migrations() -> list[tuple[str, str, str, str]]:
    rows = []
    for py in sorted(VERSIONS.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        rev = down = ""
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                tgt = node.targets[0]
                if isinstance(tgt, ast.Name) and isinstance(node.value, ast.Constant):
                    if tgt.id == "revision":
                        rev = str(node.value.value)
                    elif tgt.id == "down_revision":
                        down = "" if node.value.value is None else str(node.value.value)
        rows.append((rev, down, py.name, first_paragraph(ast.get_docstring(tree))))
    return sorted(rows)


def esc(text: str | None) -> str:
    if text is None:
        return ""
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text.replace("|", "\\|")


def code(text: str | None) -> str:
    t = esc(text)
    return f"`{t}`" if t else ""


TG_ROW, TG_BEFORE, TG_INSERT, TG_DELETE, TG_UPDATE, TG_TRUNCATE, TG_INSTEAD = (
    1, 2, 4, 8, 16, 32, 64)


def trigger_desc(tgtype: int) -> tuple[str, str, str]:
    if tgtype & TG_INSTEAD:
        timing = "INSTEAD OF"
    elif tgtype & TG_BEFORE:
        timing = "BEFORE"
    else:
        timing = "AFTER"
    events = [name for bit, name in ((TG_INSERT, "INSERT"), (TG_UPDATE, "UPDATE"),
                                     (TG_DELETE, "DELETE"), (TG_TRUNCATE, "TRUNCATE"))
              if tgtype & bit]
    level = "ROW" if tgtype & TG_ROW else "STATEMENT"
    return timing, " OR ".join(events), level


PRIV_ORDER = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES",
              "TRIGGER", "USAGE", "EXECUTE"]


def privs(names) -> str:
    s = set(names)
    out = [p for p in PRIV_ORDER if p in s] + sorted(s - set(PRIV_ORDER))
    return ", ".join(out) if out else "(none)"


def generate(cur) -> tuple[str, int]:
    out: list[str] = [HEADER]

    cur.execute("SHOW server_version_num")
    major = int(cur.fetchone()[0]) // 10000
    cur.execute("SELECT version_num FROM alembic_version")
    heads = sorted(r[0] for r in cur.fetchall())

    out += ["## Migrations", ""]
    out.append(f"Database at Alembic head **{', '.join(heads)}** "
               f"(catalog read from PostgreSQL {major}). Files in "
               "`apps/api/alembic/versions/`.")
    out += ["", "| Revision | Down | File | Summary |", "|---|---|---|---|"]
    for rev, down, fname, summary in migrations():
        out.append(f"| {rev} | {down or '-'} | `{fname}` | {esc(summary)} |")
    out.append("")

    # roles
    cur.execute(
        "SELECT rolname, rolsuper, rolbypassrls, rolcanlogin FROM pg_roles "
        "WHERE rolname = %s", (APP_ROLE,))
    r = cur.fetchone()
    out += ["## Application role", ""]
    if r:
        out.append(f"`{r[0]}`: superuser={'yes' if r[1] else 'no'}, "
                   f"bypassrls={'yes' if r[2] else 'no'}, "
                   f"login={'yes' if r[3] else 'no'}.")
    else:
        out.append(f"Role `{APP_ROLE}` not found in this cluster.")
    out.append("")

    cur.execute(
        """
        SELECT c.oid, c.relname, c.relrowsecurity, c.relforcerowsecurity,
               obj_description(c.oid, 'pg_class')
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relkind IN ('r', 'p')
        ORDER BY c.relname
        """, (SCHEMA,))
    tables = cur.fetchall()

    out += ["## Table index", "",
            "| Table | RLS | Policies | Triggers | hms_app grants |",
            "|---|---|---|---|---|"]
    summary_at = len(out)
    out.append("")
    summary_rows: list[str] = []

    out += ["## Tables", ""]
    for oid, name, rls, force, comment in tables:
        out.append(f"### {name}")
        out.append("")
        if comment:
            out.append(esc(comment))
            out.append("")
        rls_txt = ("enabled" + (" (FORCE)" if force else "")) if rls else "**disabled**"
        out.append(f"- Row-level security: {rls_txt}")

        # grants
        cur.execute(
            """
            SELECT a.privilege_type
            FROM pg_class c, aclexplode(c.relacl) a
            WHERE c.oid = %s AND a.grantee = (SELECT oid FROM pg_roles WHERE rolname = %s)
            """, (oid, APP_ROLE))
        g = privs(r[0] for r in cur.fetchall())
        out.append(f"- Grants for {APP_ROLE}: {g}")
        out.append("")

        # columns
        cur.execute(
            """
            SELECT a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull,
                   pg_get_expr(d.adbin, d.adrelid), a.attidentity, a.attgenerated
            FROM pg_attribute a
            LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
            WHERE a.attrelid = %s AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY a.attnum
            """, (oid,))
        out += ["| Column | Type | Nullable | Default |", "|---|---|---|---|"]
        for col, typ, notnull, default, ident, gen in cur.fetchall():
            if ident:
                default = "identity " + ("ALWAYS" if ident == "a" else "BY DEFAULT")
            if gen:
                default = f"generated: {default}"
            out.append(f"| `{col}` | {esc(typ)} | {'no' if notnull else 'yes'} | "
                       f"{code(default)} |")
        out.append("")

        # constraints
        cur.execute(
            """
            SELECT conname, contype, pg_get_constraintdef(oid, true)
            FROM pg_constraint WHERE conrelid = %s
            ORDER BY contype, conname
            """, (oid,))
        cons = cur.fetchall()
        labels = {"p": "Primary key", "f": "Foreign keys", "u": "Unique constraints",
                  "c": "Check constraints", "x": "Exclusion constraints"}
        for ctype in ("p", "f", "u", "c", "x"):
            items = [(n, d) for n, t, d in cons if t == ctype]
            if not items:
                continue
            if ctype == "p" and len(items) == 1:
                out.append(f"**Primary key** `{items[0][0]}`: {code(items[0][1])}")
                out.append("")
                continue
            out.append(f"**{labels[ctype]}**")
            out.append("")
            for n, d in items:
                out.append(f"- `{n}`: {code(d)}")
            out.append("")

        # indexes (those not backing a PK/unique/exclusion constraint)
        cur.execute(
            """
            SELECT ic.relname, i.indisunique, pg_get_indexdef(i.indexrelid),
                   pg_get_expr(i.indpred, i.indrelid)
            FROM pg_index i JOIN pg_class ic ON ic.oid = i.indexrelid
            WHERE i.indrelid = %s
              AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid = i.indexrelid
                              AND k.conrelid = i.indrelid)
            ORDER BY ic.relname
            """, (oid,))
        idx = cur.fetchall()
        if idx:
            out.append("**Indexes**")
            out.append("")
            for iname, uniq, idef, pred in idx:
                using = idef.split(" USING ", 1)[-1]
                if " WHERE " in using:
                    using = using.split(" WHERE ", 1)[0]
                tags = []
                if uniq:
                    tags.append("UNIQUE")
                if pred:
                    tags.append("partial")
                tag = f" ({', '.join(tags)})" if tags else ""
                line = f"- `{iname}`{tag}: {code(using)}"
                if pred:
                    line += f" WHERE {code(pred)}"
                out.append(line)
            out.append("")

        # policies
        cur.execute(
            """
            SELECT policyname, permissive, cmd, roles::text[], qual, with_check
            FROM pg_policies WHERE schemaname = %s AND tablename = %s
            ORDER BY policyname
            """, (SCHEMA, name))
        pols = cur.fetchall()
        if pols:
            out.append("**RLS policies**")
            out.append("")
            for pname, permissive, cmd, roles, qual, check in pols:
                kind = "" if permissive == "PERMISSIVE" else f" {permissive}"
                out.append(f"- `{pname}`{kind} FOR {cmd} TO {', '.join(sorted(roles))}")
                if qual:
                    out.append(f"  - USING {code(qual)}")
                if check:
                    out.append(f"  - WITH CHECK {code(check)}")
            out.append("")

        # triggers
        cur.execute(
            """
            SELECT t.tgname, t.tgtype, t.tgfoid::regprocedure::text, t.tgenabled,
                   pg_get_triggerdef(t.oid, true)
            FROM pg_trigger t
            WHERE t.tgrelid = %s AND NOT t.tgisinternal
            ORDER BY t.tgname
            """, (oid,))
        trgs = cur.fetchall()
        if trgs:
            out.append("**Triggers**")
            out.append("")
            for tname, tgtype, func, enabled, tdef in trgs:
                timing, events, level = trigger_desc(tgtype)
                m = re.search(r" UPDATE OF (.+?) ON ", tdef)
                if m:
                    events = events.replace("UPDATE", f"UPDATE OF {m.group(1)}")
                when = re.search(r" WHEN \((.*)\) EXECUTE ", tdef)
                line = f"- `{tname}`: {timing} {events} FOR EACH {level} -> `{func}`"
                if when:
                    line += f" WHEN {code(when.group(1))}"
                if enabled == "D":
                    line += " (disabled)"
                out.append(line)
            out.append("")

        summary_rows.append(
            f"| [{name}](#{name}) | {'yes' if rls else '**no**'} | "
            f"{len(pols)} | {len(trgs)} | {g} |")

    out[summary_at:summary_at] = summary_rows

    # sequences
    cur.execute(
        """
        SELECT c.relname,
               coalesce((SELECT array_agg(a.privilege_type::text)
                         FROM aclexplode(c.relacl) a
                         WHERE a.grantee = (SELECT oid FROM pg_roles WHERE rolname = %s)),
                        '{}')
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relkind = 'S'
        ORDER BY c.relname
        """, (APP_ROLE, SCHEMA))
    seqs = cur.fetchall()
    if seqs:
        out += ["## Sequences", "", f"| Sequence | {APP_ROLE} grants |", "|---|---|"]
        for sname, sp in seqs:
            out.append(f"| `{sname}` | {privs(sp)} |")
        out.append("")

    # functions
    cur.execute(
        """
        SELECT p.oid, p.proname, pg_get_function_identity_arguments(p.oid),
               pg_get_function_result(p.oid), p.prosecdef, l.lanname,
               coalesce(array_to_string(p.proconfig, ', '), ''),
               pg_get_userbyid(p.proowner),
               has_function_privilege(%s, p.oid, 'EXECUTE')
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_language l ON l.oid = p.prolang
        WHERE n.nspname = %s
        ORDER BY p.proname, pg_get_function_identity_arguments(p.oid)
        """, (APP_ROLE, SCHEMA))
    funcs = cur.fetchall()
    secdef = [f for f in funcs if f[4]]
    others = [f for f in funcs if not f[4]]
    out += ["## SECURITY DEFINER functions", ""]
    if secdef:
        out += ["| Function | Returns | Language | Config | Owner | hms_app EXECUTE |",
                "|---|---|---|---|---|---|"]
        for _oid, fname, fargs, fres, _s, lang, cfg, owner, can_exec in secdef:
            out.append(f"| `{fname}({esc(fargs)})` | {esc(fres)} | {lang} | "
                       f"{code(cfg) or '-'} | {owner} | {'yes' if can_exec else 'no'} |")
    else:
        out.append("None.")
    out.append("")
    if others:
        out += ["## Other functions (SECURITY INVOKER)", "",
                "| Function | Returns | Language |", "|---|---|---|"]
        for _oid, fname, fargs, fres, _s, lang, *_ in others:
            out.append(f"| `{fname}({esc(fargs)})` | {esc(fres)} | {lang} |")
        out.append("")

    # seeded RBAC catalogue
    cur.execute("SELECT to_regclass('public.roles'), to_regclass('public.permissions')")
    if all(cur.fetchone()):
        cur.execute("SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'roles'")
        rcols = {r[0] for r in cur.fetchall()}
        where = "WHERE r.organization_id IS NULL" if "organization_id" in rcols else ""
        cur.execute(
            f"""
            SELECT r.key, coalesce(array_agg(rp.permission_key ORDER BY rp.permission_key)
                                   FILTER (WHERE rp.permission_key IS NOT NULL), '{{}}')
            FROM roles r LEFT JOIN role_permissions rp ON rp.role_id = r.id
            {where}
            GROUP BY r.key ORDER BY r.key
            """)
        role_rows = cur.fetchall()
        cur.execute("SELECT key FROM permissions ORDER BY key")
        perm_keys = [r[0] for r in cur.fetchall()]
        out += ["## Seeded RBAC catalogue", "",
                f"{len(perm_keys)} permission keys (seeded by migrations):", "",
                ", ".join(f"`{k}`" for k in perm_keys), "",
                "| System role | Permissions |", "|---|---|"]
        for rkey, plist in role_rows:
            out.append(f"| `{rkey}` | {', '.join(plist) if plist else '(none)'} |")
        out.append("")

    return "\n".join(out).rstrip("\n") + "\n", len(tables)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dsn", required=True,
                    help="libpq DSN/URL of a freshly migrated DB, as the owner role")
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    args = ap.parse_args()
    dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", args.dsn)
    conn = psycopg2.connect(dsn)
    try:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            text, n = generate(cur)
    finally:
        conn.close()
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out.name}: {n} tables", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
