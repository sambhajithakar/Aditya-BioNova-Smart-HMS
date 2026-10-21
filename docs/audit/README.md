# Audit evidence (2026-10-20)

Detailed, line-referenced findings from the four review streams behind
[../../AUDIT_REPORT.md](../../AUDIT_REPORT.md):

| File | Scope |
|---|---|
| [A1_backend_security.md](A1_backend_security.md) | Auth, tenancy, RLS, RBAC, audit trail, migrations |
| [A2_backend_domain.md](A2_backend_domain.md) | Patients → IPD domain modules, services, reports |
| [A3_web.md](A3_web.md) | Next.js web portal |
| [A4_mobile_infra.md](A4_mobile_infra.md) | Flutter Android app, Docker, CI, deployment |

These are **static code reviews**. Where a file says "no tests run", that refers
to the reviewer itself; the real executed results (102/102 API tests, lint,
build, migrations, dependency scans, and runtime probes of the top defects) are
recorded in AUDIT_REPORT.md §3–§4. Findings not marked "Proven" there were
verified by reading code, not by execution.
