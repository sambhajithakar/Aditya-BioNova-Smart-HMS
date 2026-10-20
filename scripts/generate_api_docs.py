#!/usr/bin/env python3
"""Generate API_DOCUMENTATION.md from packages/contracts/openapi.json.

The OpenAPI snapshot (itself generated from the FastAPI app by
scripts/generate-contracts.sh) is the source of truth for paths, methods,
parameters and schemas. Required permissions are recovered by statically
parsing apps/api/app/routers/*.py (no imports, no database): a route's
permission is listed only when its handler signature contains
``Depends(require_permission("..."))`` and the handler can be matched to the
OpenAPI operation by method + full path AND by operationId prefix. Anything
that cannot be matched that way is shown as "-" rather than guessed.

Output is deterministic (sorted, no timestamps) so CI can diff it:

    python scripts/generate_api_docs.py
    git diff --exit-code API_DOCUMENTATION.md

Standard library only.
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / "packages" / "contracts" / "openapi.json"
ROUTERS = ROOT / "apps" / "api" / "app" / "routers"
OUT = ROOT / "API_DOCUMENTATION.md"
BASE_PREFIX = "/api/v1"
METHODS = ("get", "post", "put", "patch", "delete")

INTRO = """\
# API Documentation

> **Generated file.** Everything below the "Endpoints" heading is produced by
> `scripts/generate_api_docs.py` from `packages/contracts/openapi.json`
> (which `scripts/generate-contracts.sh` exports from the FastAPI app).
> Do not edit by hand: regenerate with
> `scripts/generate-contracts.sh && python3 scripts/generate_api_docs.py`.
> CI (`contracts` job) fails when this file is stale. The overview section is
> maintained inside the generator script.

Interactive docs (development only): `http://127.0.0.1:8000/api/v1/docs`.
Machine-readable spec: `packages/contracts/openapi.json`.

## Overview

### Base path and format

- Every endpoint lives under **`/api/v1`**. JSON request and response bodies
  (`Content-Type: application/json`).
- Every response carries `X-Request-ID` (the correlation id). A client may send
  its own `X-Request-ID`; otherwise the server generates one.
- The tenant (organization) is **never** taken from the client. It comes from
  the verified access token; there is no `organization_id` request parameter.
- List endpoints page with `limit` / `offset` query parameters.

### Authentication

- `Authorization: Bearer <access_token>`. Access tokens are short-lived JWTs
  (**30 minutes** by default, `ACCESS_TOKEN_TTL_SECONDS=1800`) bound to a
  server-side session; logout or session
  revocation invalidates them immediately.
- Refresh tokens are **rotating**: `POST /api/v1/auth/refresh` returns a new
  pair and retires the old refresh token. Replaying a retired refresh token
  revokes the whole session family (reuse detection) and is audited.
- **MFA challenge flow.** When the account has TOTP enabled,
  `POST /api/v1/auth/login` (and `POST /api/v1/auth/invitations/accept`)
  answers `200` with `{"mfa_required": true, "mfa_token": "...",
  "methods": ["totp"], "expires_in": ...}` instead of a token pair. The client
  then calls `POST /api/v1/auth/mfa/verify` with the `mfa_token` and a TOTP or
  recovery code to obtain the session.
- "Permission" in the tables below is the RBAC permission key the caller's
  role must hold (`403 Missing permission: <key>` otherwise); handlers may
  apply further business rules on top. "authenticated"
  means any valid session; "public" means no token is required; "-" means the
  generator could not determine it statically.

### Idempotency

Create endpoints marked **Idempotency-Key: yes** accept an optional
`Idempotency-Key` header. A retry with the same key and the same payload
replays the stored response; the same key with a different payload returns
`409`. Keys are scoped to the organization.

### Errors

Error bodies are JSON with a `detail` field (a string, or a list of field
errors for `422`). Errors raised by the database layer (trigger guards,
constraint violations) and `500`s use `{"detail": ..., "correlation_id": "..."}`;
for all errors the correlation id is also in the `X-Request-ID` response
header. Status codes used across the API:

- **400** - invalid or expired one-time token (password reset link,
  invitation).
- **401** - missing/invalid/expired access token or revoked session; login
  failures are generic (no account enumeration).
- **403** - authenticated but the role lacks the required permission, or the
  action is not allowed for the role.
- **404** - not found. **Resources of another tenant also return 404**
  (never 403), so ids cannot be probed across organizations.
- **409** - conflict: duplicates, Idempotency-Key reuse with a different
  payload, state-machine / append-only violations raised by database
  triggers, concurrent update (retry).
- **422** - validation error (request schema, or database value
  constraints such as NOT NULL / length / range).
- **429** - rate limited (login, MFA, password reset, ...); the response
  carries a `Retry-After` header (seconds).
- **500** - internal error; the body contains only a generic message and
  `correlation_id`.

### Development-only endpoints

`GET /api/v1/dev/outbox` (tag `dev`) exposes the outbound message outbox
(password reset, invitation e-mails) so they can be read without a mail
server. The router is mounted **only when the environment is development**;
it does not exist in staging or production builds.
"""


# ---------------------------------------------------------------------------
# Permission discovery (static AST parse of the routers)
# ---------------------------------------------------------------------------

def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name):
            return f.id
        if isinstance(f, ast.Attribute):
            return f.attr
    return None


def _guards_in(nodes: list[ast.AST]) -> tuple[set[str], bool]:
    """Return (permission keys, authenticated) found in Depends(...) calls."""
    perms: set[str] = set()
    authed = False
    for top in nodes:
        for node in ast.walk(top):
            if _call_name(node) != "Depends" or not node.args:
                continue
            dep = node.args[0]
            if _call_name(dep) == "require_permission" and dep.args:
                key = _const_str(dep.args[0])
                if key is None:
                    return set(), False  # dynamic key: do not guess
                perms.add(key)
            elif isinstance(dep, ast.Name) and dep.id == "get_current_principal":
                authed = True
    return perms, authed


def discover_guards() -> dict[tuple[str, str], tuple[str, str]]:
    """Map (METHOD, full path) -> (handler function name, guard label)."""
    found: dict[tuple[str, str], tuple[str, str]] = {}
    for py in sorted(ROUTERS.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        prefix = ""
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and _call_name(node.value) == "APIRouter"
            ):
                for kw in node.value.keywords:
                    if kw.arg == "prefix":
                        prefix = _const_str(kw.value) or ""
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == "router"
                    and dec.func.attr in METHODS
                    and dec.args
                ):
                    continue
                sub = _const_str(dec.args[0])
                if sub is None:
                    continue
                dep_nodes: list[ast.AST] = list(node.args.defaults)
                dep_nodes += [d for d in node.args.kw_defaults if d is not None]
                dep_nodes += [kw.value for kw in dec.keywords if kw.arg == "dependencies"]
                perms, authed = _guards_in(dep_nodes)
                if perms:
                    label = " + ".join(f"`{p}`" for p in sorted(perms))
                elif authed:
                    label = "authenticated"
                else:
                    label = "public"
                key = (dec.func.attr.upper(), BASE_PREFIX + prefix + sub)
                if key in found:
                    # ambiguous (same route declared twice): refuse to guess
                    found[key] = ("", "-")
                else:
                    found[key] = (node.name, label)
    return found


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def schema_name(s: dict | None) -> str:
    if not s:
        return "-"
    if "$ref" in s:
        return s["$ref"].rsplit("/", 1)[-1]
    for comb in ("anyOf", "oneOf"):
        if comb in s:
            return " | ".join(schema_name(x) for x in s[comb])
    if "allOf" in s:
        return " & ".join(schema_name(x) for x in s["allOf"])
    t = s.get("type")
    if t == "array":
        return f"list[{schema_name(s.get('items'))}]"
    if t == "object":
        add = s.get("additionalProperties")
        if isinstance(add, dict) and add:
            return f"dict[str, {schema_name(add)}]"
        return "object"
    if t:
        fmt = s.get("format")
        return f"{t}({fmt})" if fmt else str(t)
    if "const" in s:
        return json.dumps(s["const"])
    return "any"


def param_type(s: dict | None) -> str:
    if not s:
        return "any"
    name = schema_name(s)
    if "enum" in s:
        name += " (" + ", ".join(str(v) for v in s["enum"]) + ")"
    return name


def body_schema(op: dict) -> str:
    rb = op.get("requestBody")
    if not rb:
        return "-"
    parts = []
    for ctype in sorted(rb.get("content", {})):
        name = schema_name(rb["content"][ctype].get("schema"))
        parts.append(name if ctype == "application/json" else f"{name} ({ctype})")
    return ", ".join(parts) or "-"


def success_responses(op: dict) -> str:
    parts = []
    for code in sorted(op.get("responses", {})):
        if not code.startswith("2"):
            continue
        content = op["responses"][code].get("content") or {}
        js = content.get("application/json", {}).get("schema")
        name = schema_name(js) if js else "(no body)"
        if name == "any":
            name = "JSON"
        parts.append(f"{code} {name}")
    return "; ".join(parts) or "-"


def first_line(text: str | None) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def esc(text: str) -> str:
    return text.replace("|", "\\|")


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render(spec: dict) -> tuple[str, int, list[str]]:
    guards = discover_guards()
    unmapped: list[str] = []
    by_tag: dict[str, list[tuple[str, str, dict]]] = {}
    total = 0
    for path, item in spec.get("paths", {}).items():
        for method, op in item.items():
            if method not in METHODS:
                continue
            tag = (op.get("tags") or ["untagged"])[0]
            by_tag.setdefault(tag, []).append((path, method.upper(), op))
            total += 1

    out = [INTRO, "## Endpoints", ""]
    info = spec.get("info", {})
    out.append(
        f"Spec: **{info.get('title', '')}** version `{info.get('version', '')}`, "
        f"OpenAPI {spec.get('openapi', '')}. {total} operations in "
        f"{len(by_tag)} tags."
    )
    out.append("")
    out.append("### Summary")
    out.append("")
    out.append("| Tag | Method | Path | Permission | Idempotency-Key |")
    out.append("|---|---|---|---|---|")
    rows = []
    details = []
    for tag in sorted(by_tag):
        ops = sorted(by_tag[tag], key=lambda x: (x[0], METHODS.index(x[1].lower())))
        details.append(f"### {tag}")
        details.append("")
        for path, method, op in ops:
            fn, label = guards.get((method, path), ("", "-"))
            op_id = op.get("operationId", "")
            if not fn or not op_id.startswith(fn + "_"):
                if label != "-" or not fn:
                    unmapped.append(f"{method} {path}")
                label = "-"
            params = op.get("parameters", [])
            idem = any(
                p.get("in") == "header" and p.get("name", "").lower() == "idempotency-key"
                for p in params
            )
            rows.append(
                f"| {tag} | {method} | `{path}` | {label} | {'yes' if idem else ''} |"
            )
            details.append(f"#### `{method} {path}`")
            details.append("")
            summary = first_line(op.get("summary"))
            desc = first_line(op.get("description"))
            if summary:
                details.append(f"**{esc(summary)}**" + (f" - {desc}" if desc else ""))
                details.append("")
            details.append(f"- Permission: {label}")
            details.append(f"- operationId: `{op_id}`")
            if idem:
                details.append("- Idempotency-Key: supported")
            rb = body_schema(op)
            details.append(f"- Request body: {rb if rb == '-' else '`' + rb + '`'}")
            details.append(f"- Response: `{success_responses(op)}`")
            visible = [
                p for p in params
                if not (p.get("in") == "header"
                        and p.get("name", "").lower() == "idempotency-key")
            ]
            if visible:
                details.append("")
                details.append("| Parameter | In | Type | Required |")
                details.append("|---|---|---|---|")
                order = {"path": 0, "query": 1, "header": 2, "cookie": 3}
                for p in sorted(visible, key=lambda x: (order.get(x.get("in"), 9),
                                                        x.get("name", ""))):
                    details.append(
                        f"| `{p.get('name')}` | {p.get('in')} | "
                        f"{esc(param_type(p.get('schema')))} | "
                        f"{'yes' if p.get('required') else 'no'} |"
                    )
            details.append("")
    out.extend(rows)
    out.append("")
    out.extend(details)

    schemas = spec.get("components", {}).get("schemas", {})
    if schemas:
        out.append("## Schemas")
        out.append("")
        out.append(
            "Field lists of the request/response schemas referenced above "
            "(`*` = required)."
        )
        out.append("")
        for name in sorted(schemas):
            s = schemas[name]
            out.append(f"### {name}")
            out.append("")
            if "enum" in s:
                out.append("Enum: " + ", ".join(f"`{v}`" for v in s["enum"]))
                out.append("")
                continue
            props = s.get("properties") or {}
            if not props:
                out.append(f"Type: `{schema_name(s)}`")
                out.append("")
                continue
            req = set(s.get("required", []))
            out.append("| Field | Type |")
            out.append("|---|---|")
            for field in props:  # declaration order is meaningful and stable
                star = "*" if field in req else ""
                out.append(f"| `{field}`{star} | {esc(param_type(props[field]))} |")
            out.append("")

    text = "\n".join(out).rstrip("\n") + "\n"
    return text, total, sorted(set(unmapped))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--spec", type=pathlib.Path, default=SPEC)
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    args = ap.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    text, total, unmapped = render(spec)
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out.name}: {total} operations", file=sys.stderr)
    if unmapped:
        print("permission not mapped (shown as '-'):", file=sys.stderr)
        for u in unmapped:
            print(f"  {u}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
