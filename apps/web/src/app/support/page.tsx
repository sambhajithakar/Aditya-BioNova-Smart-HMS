"use client";

/**
 * Support (M7.1, tenant side): the organization's tickets, a new-ticket form
 * and the selected ticket's conversation with reply / close. Tickets go to
 * the vendor, so the page warns clearly never to include patient data.
 * Reading needs support.read, writing support.write.
 */
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Messages, TicketThread, fmtDateTime, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { useCan } from "@/lib/me";
import {
  SupportTicket,
  SupportTicketDetail,
  TICKET_CATEGORIES,
  TICKET_PRIORITIES,
  serverMessage,
} from "@/lib/saas";

const EMPTY = { subject: "", category: "technical", priority: "normal", body: "" };

function SupportBody() {
  const { t } = useLang();
  const can = useCan();
  const write = can("support.write");
  const { busy, error, notice, setError, setNotice, act } = useAction();
  const [tickets, setTickets] = useState<SupportTicket[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [selected, setSelected] = useState<SupportTicketDetail | null>(null);
  const [reply, setReply] = useState("");

  const load = useCallback(async () => {
    try {
      setTickets(await api.get<SupportTicket[]>("/support/tickets"));
    } catch (err) {
      setError(serverMessage(err, t("loadFailed")));
    }
  }, [setError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const open = (id: string) =>
    void act(async () => {
      setSelected(await api.get<SupportTicketDetail>(`/support/tickets/${id}`));
      setReply("");
    });

  const onCreate = (e: FormEvent) => {
    e.preventDefault();
    void act(async () => {
      const tk = await api.post<SupportTicket>("/support/tickets", {
        subject: form.subject.trim(),
        category: form.category,
        priority: form.priority,
        body: form.body.trim(),
      });
      setForm(EMPTY);
      setNotice(`${t("ticketCreated")} #${tk.number}`);
      await load();
      setSelected(await api.get<SupportTicketDetail>(`/support/tickets/${tk.id}`));
    });
  };

  const onReply = (e: FormEvent) => {
    e.preventDefault();
    if (!selected) return;
    void act(async () => {
      setSelected(
        await api.post<SupportTicketDetail>(`/support/tickets/${selected.id}/messages`, {
          body: reply.trim(),
        }),
      );
      setReply("");
      await load();
    });
  };

  const onClose = () => {
    if (!selected) return;
    void act(async () => {
      await api.post<SupportTicket>(`/support/tickets/${selected.id}/close`, {});
      setSelected(await api.get<SupportTicketDetail>(`/support/tickets/${selected.id}`));
      await load();
    });
  };

  return (
    <main className="page">
      <h1 style={{ marginTop: 0 }}>{t("navSupport")}</h1>
      <p className="warn-box" role="note" data-testid="no-patient-data">
        <strong>⚠ {t("noPatientData")}</strong>
      </p>
      <Messages error={error} notice={notice} />

      <section className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t("ticketNo")}</th>
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
                  <td colSpan={6} className="muted">
                    {t("noTickets")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {selected && (
        <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="ticket-h">
          <h2 id="ticket-h" style={{ marginTop: 0 }}>
            #{selected.number} — {selected.subject}
          </h2>
          <p className="muted" style={{ margin: 0 }}>
            {t(`ticketCat_${selected.category}`)} · {t(`ticketPri_${selected.priority}`)} ·{" "}
            <span data-testid="ticket-status">{t(`ticketStatus_${selected.status}`)}</span>
            {selected.created_by_name && (
              <>
                {" "}
                · {t("createdBy")}: {selected.created_by_name}
              </>
            )}
          </p>
          <TicketThread ticket={selected} />
          {write && selected.status !== "closed" && (
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
              <div className="row">
                <button type="submit" className="primary" disabled={busy || !reply.trim()}>
                  {t("sendReply")}
                </button>
                <button type="button" className="danger" disabled={busy} onClick={onClose}>
                  {t("closeTicket")}
                </button>
              </div>
            </form>
          )}
        </section>
      )}

      {write && (
        <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="new-ticket-h">
          <h2 id="new-ticket-h" style={{ marginTop: 0 }}>
            {t("newTicket")}
          </h2>
          <form className="stack" onSubmit={onCreate} style={{ maxWidth: 640 }}>
            <label className="field">
              {t("subject")}
              <input
                type="text"
                value={form.subject}
                maxLength={200}
                onChange={(e) => setForm({ ...form, subject: e.target.value })}
                required
              />
            </label>
            <div className="grid two">
              <label className="field">
                {t("category")}
                <select
                  value={form.category}
                  onChange={(e) => setForm({ ...form, category: e.target.value })}
                >
                  {TICKET_CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {t(`ticketCat_${c}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                {t("priority")}
                <select
                  value={form.priority}
                  onChange={(e) => setForm({ ...form, priority: e.target.value })}
                >
                  {TICKET_PRIORITIES.map((p) => (
                    <option key={p} value={p}>
                      {t(`ticketPri_${p}`)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="field">
              {t("message")}
              <textarea
                className="wide"
                rows={5}
                maxLength={5000}
                value={form.body}
                onChange={(e) => setForm({ ...form, body: e.target.value })}
                required
                aria-describedby="no-phi-hint"
              />
              <span id="no-phi-hint" className="field-error">
                {t("noPatientData")}
              </span>
            </label>
            <button type="submit" className="primary" disabled={busy}>
              {t("newTicket")}
            </button>
          </form>
        </section>
      )}
    </main>
  );
}

export default function SupportPage() {
  return (
    <AppShell active="support">
      <SupportBody />
    </AppShell>
  );
}
