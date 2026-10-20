"use client";

/**
 * Audit log viewer (needs audit.read): GET /audit-events?action=&limit=&offset=
 * → Page{items: AuditEventOut[], total, limit, offset}, newest first. The
 * action filter is an exact match on the server.
 */
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Messages, fmtDateTime, useAction } from "@/components/Saas";
import { PageOf, api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { AuditEvent, serverMessage } from "@/lib/saas";

const PAGE_SIZE = 50;

function shortJson(v: Record<string, unknown> | null | undefined): string {
  if (!v || Object.keys(v).length === 0) return "—";
  const s = JSON.stringify(v);
  return s.length > 160 ? `${s.slice(0, 157)}…` : s;
}

function AuditBody() {
  const { t } = useLang();
  const { error, setError } = useAction();
  const [page, setPage] = useState<PageOf<AuditEvent> | null>(null);
  const [offset, setOffset] = useState(0);
  const [filterInput, setFilterInput] = useState("");
  const [action, setAction] = useState("");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const q = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
      if (action) q.set("action", action);
      setPage(await api.get<PageOf<AuditEvent>>(`/audit-events?${q.toString()}`));
    } catch (err) {
      setError(serverMessage(err, t("loadFailed")));
    } finally {
      setLoading(false);
    }
  }, [action, offset, setError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const onFilter = (e: FormEvent) => {
    e.preventDefault();
    setOffset(0);
    setAction(filterInput.trim().slice(0, 80));
  };

  const total = page?.total ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + PAGE_SIZE, total);

  return (
    <main className="page">
      <h1 style={{ marginTop: 0 }}>{t("navAudit")}</h1>
      <Messages error={error} notice={null} />

      <form className="row" onSubmit={onFilter} style={{ marginBottom: "1rem", alignItems: "flex-end" }}>
        <label className="field grow">
          {t("actionFilter")}
          <input
            type="search"
            value={filterInput}
            maxLength={80}
            placeholder="auth.login"
            onChange={(e) => setFilterInput(e.target.value)}
          />
        </label>
        <button type="submit" className="primary">
          {t("applyFilter")}
        </button>
        {action && (
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setFilterInput("");
              setAction("");
              setOffset(0);
            }}
          >
            {t("clearFilter")}
          </button>
        )}
      </form>

      <section className="card">
        <div className="table-wrap">
          <table data-testid="audit-table">
            <thead>
              <tr>
                <th scope="col">{t("time")}</th>
                <th scope="col">{t("auditAction")}</th>
                <th scope="col">{t("actor")}</th>
                <th scope="col">{t("resource")}</th>
                <th scope="col">{t("details")}</th>
                <th scope="col">{t("correlationId")}</th>
              </tr>
            </thead>
            <tbody>
              {page?.items.map((ev) => (
                <tr key={ev.id}>
                  <td>{fmtDateTime(ev.created_at)}</td>
                  <td>
                    <code>{ev.action}</code>
                  </td>
                  <td title={ev.actor_user_id ?? undefined}>
                    {ev.actor_user_id ? ev.actor_user_id.slice(0, 8) : "—"}
                  </td>
                  <td>
                    {ev.resource_type ?? "—"}
                    {ev.resource_id && (
                      <span className="muted" title={ev.resource_id}>
                        {" "}
                        {ev.resource_id.slice(0, 12)}
                      </span>
                    )}
                  </td>
                  <td style={{ fontFamily: "ui-monospace, monospace", fontSize: "0.85rem" }}>
                    {shortJson(ev.metadata)}
                  </td>
                  <td className="muted">{ev.correlation_id ? ev.correlation_id.slice(0, 12) : "—"}</td>
                </tr>
              ))}
              {page && page.items.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted">
                    {t("noEvents")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <nav className="pager" aria-label={t("navAudit")}>
          <button
            type="button"
            className="secondary"
            disabled={loading || offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            ← {t("previous")}
          </button>
          <span aria-live="polite">
            {t("showing")} {from}–{to} / {total}
          </span>
          <button
            type="button"
            className="secondary"
            disabled={loading || offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            {t("nextPage")} →
          </button>
        </nav>
      </section>
    </main>
  );
}

export default function AuditPage() {
  return (
    <AppShell active="audit">
      <AuditBody />
    </AppShell>
  );
}
