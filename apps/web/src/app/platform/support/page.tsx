"use client";

/**
 * Platform console — support queue across all tenants
 * (GET /platform/support/tickets?status=) and the selected ticket: the full
 * conversation including internal notes, a reply box with an "internal note"
 * toggle (internal notes are never shown to the clinic) and status /
 * priority changes.
 */
import { FormEvent, useCallback, useEffect, useState } from "react";
import { PlatformShell } from "@/components/PlatformShell";
import { Messages, TicketThread, fmtDateTime, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import {
  SupportTicket,
  SupportTicketDetail,
  TICKET_PRIORITIES,
  TICKET_STATUSES,
  serverMessage,
} from "@/lib/saas";

function QueueBody() {
  const { t } = useLang();
  const { busy, error, notice, setError, setNotice, act } = useAction();
  const [status, setStatus] = useState("");
  const [tickets, setTickets] = useState<SupportTicket[]>([]);
  const [selected, setSelected] = useState<SupportTicketDetail | null>(null);
  const [reply, setReply] = useState("");
  const [internal, setInternal] = useState(false);
  const [meta, setMeta] = useState({ status: "", priority: "" });

  const load = useCallback(async () => {
    try {
      const qs = status ? `?status=${encodeURIComponent(status)}` : "";
      setTickets(await api.get<SupportTicket[]>(`/platform/support/tickets${qs}`));
    } catch (err) {
      setError(serverMessage(err, t("loadFailed")));
    }
  }, [status, setError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const show = (d: SupportTicketDetail) => {
    setSelected(d);
    setMeta({ status: d.status, priority: d.priority });
  };

  const open = (id: string) =>
    void act(async () => {
      show(await api.get<SupportTicketDetail>(`/platform/support/tickets/${encodeURIComponent(id)}`));
      setReply("");
      setInternal(false);
    });

  const onReply = (e: FormEvent) => {
    e.preventDefault();
    if (!selected) return;
    void act(async () => {
      show(
        await api.post<SupportTicketDetail>(
          `/platform/support/tickets/${encodeURIComponent(selected.id)}/messages`,
          { body: reply.trim(), internal },
        ),
      );
      setReply("");
      setInternal(false);
      await load();
    });
  };

  const onMeta = (e: FormEvent) => {
    e.preventDefault();
    if (!selected) return;
    const body: Record<string, string> = {};
    if (meta.status !== selected.status) body.status = meta.status;
    if (meta.priority !== selected.priority) body.priority = meta.priority;
    if (Object.keys(body).length === 0) return;
    void act(async () => {
      const id = encodeURIComponent(selected.id);
      await api.patch<SupportTicket>(`/platform/support/tickets/${id}`, body);
      show(await api.get<SupportTicketDetail>(`/platform/support/tickets/${id}`));
      setNotice(t("saved"));
      await load();
    });
  };

  return (
    <main className="page" style={{ maxWidth: 1280 }}>
      <h1 style={{ marginTop: 0 }}>{t("platformSupport")}</h1>
      <Messages error={error} notice={notice} />

      <section className="card">
        <label className="field" style={{ maxWidth: 320, marginBottom: "0.75rem" }}>
          {t("status")}
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">{t("allStatuses")}</option>
            {TICKET_STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`ticketStatus_${s}`)}
              </option>
            ))}
          </select>
        </label>
        <div className="table-wrap">
          <table data-testid="platform-tickets">
            <thead>
              <tr>
                <th scope="col">{t("ticketNo")}</th>
                <th scope="col">{t("tenant")}</th>
                <th scope="col">{t("subject")}</th>
                <th scope="col">{t("category")}</th>
                <th scope="col">{t("priority")}</th>
                <th scope="col">{t("status")}</th>
                <th scope="col">{t("updatedAt")}</th>
              </tr>
            </thead>
            <tbody>
              {tickets.map((tk) => (
                <tr key={tk.id} className={selected?.id === tk.id ? "selected" : undefined}>
                  <td>#{tk.number}</td>
                  <td>{tk.organization_name ?? "—"}</td>
                  <td>
                    <button type="button" className="ghost" onClick={() => open(tk.id)}>
                      {tk.subject}
                    </button>
                  </td>
                  <td>{t(`ticketCat_${tk.category}`)}</td>
                  <td>{t(`ticketPri_${tk.priority}`)}</td>
                  <td>
                    <span className="tag">{t(`ticketStatus_${tk.status}`)}</span>
                  </td>
                  <td>{fmtDateTime(tk.updated_at)}</td>
                </tr>
              ))}
              {tickets.length === 0 && (
                <tr>
                  <td colSpan={7} className="muted">
                    {t("noTickets")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {selected && (
        <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="pticket-h">
          <h2 id="pticket-h" style={{ marginTop: 0 }}>
            #{selected.number} — {selected.subject}
          </h2>
          <p className="muted" style={{ margin: 0 }}>
            {selected.organization_name ?? ""} · {t(`ticketCat_${selected.category}`)}
            {selected.created_by_name && (
              <>
                {" "}
                · {t("createdBy")}: {selected.created_by_name}
              </>
            )}
          </p>

          <form className="row" onSubmit={onMeta} style={{ alignItems: "flex-end", marginTop: "0.75rem" }}>
            <label className="field">
              {t("status")}
              <select value={meta.status} onChange={(e) => setMeta({ ...meta, status: e.target.value })}>
                {TICKET_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {t(`ticketStatus_${s}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              {t("priority")}
              <select
                value={meta.priority}
                onChange={(e) => setMeta({ ...meta, priority: e.target.value })}
              >
                {TICKET_PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {t(`ticketPri_${p}`)}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit" className="secondary" disabled={busy}>
              {t("update")}
            </button>
          </form>

          <TicketThread ticket={selected} />

          <form className="stack" onSubmit={onReply} style={{ maxWidth: "none" }}>
            <label className="field">
              {t("reply")}
              <textarea
                className="wide"
                rows={3}
                maxLength={5000}
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                required
              />
            </label>
            <label className="inline">
              <input
                type="checkbox"
                checked={internal}
                onChange={(e) => setInternal(e.target.checked)}
              />
              {t("internalNote")}
            </label>
            <button type="submit" className="primary" disabled={busy || !reply.trim()}>
              {t("sendReply")}
            </button>
          </form>
        </section>
      )}
    </main>
  );
}

export default function PlatformSupportPage() {
  return (
    <PlatformShell active="support">
      <QueueBody />
    </PlatformShell>
  );
}
