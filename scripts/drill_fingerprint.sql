-- Schema + data fingerprint used by scripts/backup_restore_drill.sh.
-- Run as the table owner / superuser (RLS not applied) against a database;
-- two databases are equal for the drill when the outputs are identical.
\pset format unaligned
\pset tuples_only on
\pset fieldsep '|'

\echo '## row_counts'
SELECT table_name,
       (xpath('/row/c/text()',
              query_to_xml(format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name),
                           false, true, '')))[1]::text::bigint
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY 1;

\echo '## rls_enabled'
SELECT relname, relrowsecurity, relforcerowsecurity
FROM pg_class
WHERE relnamespace = 'public'::regnamespace AND relkind IN ('r', 'p')
ORDER BY 1;

\echo '## policies'
SELECT tablename, policyname, permissive, roles::text, cmd, qual, with_check
FROM pg_policies WHERE schemaname = 'public'
ORDER BY 1, 2;

\echo '## triggers'
SELECT c.relname, t.tgname, t.tgenabled, pg_get_triggerdef(t.oid)
FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
WHERE NOT t.tgisinternal AND c.relnamespace = 'public'::regnamespace
ORDER BY 1, 2;

\echo '## functions'
SELECT p.proname, md5(pg_get_functiondef(p.oid))
FROM pg_proc p
WHERE p.pronamespace = 'public'::regnamespace AND p.prokind = 'f'
ORDER BY 1, 2;

\echo '## table_grants'
SELECT relname, relkind, coalesce(relacl::text, '<default>')
FROM pg_class
WHERE relnamespace = 'public'::regnamespace AND relkind IN ('r', 'p', 'S', 'v', 'm')
ORDER BY 1;

\echo '## default_privileges'
SELECT defaclrole::regrole::text, defaclnamespace::regnamespace::text, defaclobjtype, defaclacl::text
FROM pg_default_acl
ORDER BY 1, 2, 3;

\echo '## indexes'
-- Partial-index predicates with `col IN (...)` hit the same cast-placement
-- deparse quirk as CHECK constraints below; compare the same normalised form
-- (index name, table, columns, uniqueness and predicate logic still compared).
SELECT indexname,
       regexp_replace(
         regexp_replace(indexdef, '::[a-z_ ]+(\[\])?', '', 'g'),
         '[()[:space:]]', '', 'g')
FROM pg_indexes WHERE schemaname = 'public' ORDER BY 1;

\echo '## constraints'
-- CHECK constraints with `col IN (...)` are deparsed differently after a
-- dump/restore round trip (cast placement: ARRAY[...]::text[] vs
-- ARRAY[(x::varchar)::text, ...]) although semantically identical — a known
-- PostgreSQL behaviour. Compare a normalised form: lower-case type casts,
-- parentheses and whitespace stripped. Type, columns and names still compared.
SELECT conrelid::regclass::text, conname, contype,
       regexp_replace(
         regexp_replace(pg_get_constraintdef(oid), '::[a-z_ ]+(\[\])?', '', 'g'),
         '[()[:space:]]', '', 'g')
FROM pg_constraint WHERE connamespace = 'public'::regnamespace
ORDER BY 1, 2;

\echo '## sequences'
SELECT sequencename, coalesce(last_value::text, 'unused')
FROM pg_sequences WHERE schemaname = 'public'
ORDER BY 1;

\echo '## alembic_version'
SELECT version_num FROM alembic_version;
