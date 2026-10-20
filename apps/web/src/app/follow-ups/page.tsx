"use client";

/**
 * Follow-up worklist (reception / doctors): due today, overdue, upcoming and
 * closed follow-ups with book / complete / missed / cancel / remind actions,
 * a clinician form to plan a follow-up, and missed appointments with an
 * optional consent-aware "we missed you" message (mock outbox by default).
 */
import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { PatientPicker } from "@/components/PatientPicker";
import { Messages, fmtDate, fmtDateTime, useAction } from "@/components/Saas";
import { Appointment, PageOf, api } from "@/lib/api";
import {
  FOLLOWUP_ACTIONS,
  FOLLOWUP_BUCKETS,
  FOLLOWUP_REASONS,
  FollowUp,
  FollowUpBucket,
  MissedAppointment,
  SendResult,
  isoDay,
} from "@/lib/comms";
import { useLang } from "@/lib/lang";
import { useCan } from "@/lib/me";
import { serverMessage } from "@/lib/saas";

type Summary = { due_today: number; overdue: number; upcoming: number; missed_appointments: number };

function FollowUpsBody() {
  const { t } = useLang();
  const can = useCan();
  const write = can("followup.write");
  const create = can("followup.create");
  const sendPerm = can("comms.send");
  const { busy, error, notice, setError, setNotice, act } = useAction();
  const [bucket, setBucket] = useState<FollowUpBucket>("due_today");
  const [rows, setRows] = useState<FollowUp[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [missed, setMissed] = useState<MissedAppointment[]>([]);
  const [booking, setBooking] = useState<{ fu: FollowUp; appts: Appointment[] } | null>(null);
  const [form, setForm] = useState({ patient_id: "", due_date: "", reason: FOLLOWUP_REASONS[0] });

  const load = useCallback(async () => {
    const [list, sum, miss] = await Promise.all([
      api.get<FollowUp[]>(`/follow-ups?bucket=${bucket}`),
      api.get<Summary>("/follow-ups/summary"),
      api.get<MissedAppointment[]>("/follow-ups/missed-appointments"),
    ]);
    setRows(list);
    setSummary(sum);
    setMissed(miss);
  }, [bucket]);

  useEffect(() => {
    load().catch((err) => setError(serverMessage(err, t("loadFailed"))));
  }, [load, setError, t]);

  const sentNotice = (r: SendResult) =>
    `${r.results.map((x) => `${t(`channel_${x.channel}`)}: ${t(`dstatus_${x.status}`)}`).join(" · ")} — ${r.mock_notice}`;

  const action = (fu: FollowUp, name: string) =>
    void act(async () => {
      if (name === "book") {
        const page = await api.get<PageOf<Appointment>>(
          `/appointments?patient_id=${fu.patient_id}&status_filter=scheduled&limit=50`,
        );
        setBooking({ fu, appts: page.items });
        return;
      }
      if (name === "remind") {
        setNotice(sentNotice(await api.post<SendResult>(`/follow-ups/${fu.id}/remind`, {})));
      } else {
        await api.post<FollowUp>(`/follow-ups/${fu.id}/${name}`, {});
      }
      await load();
    });

  const book = (appointmentId: string) =>
    void act(async () => {
      if (!booking) return;
      await api.post<FollowUp>(`/follow-ups/${booking.fu.id}/book`, { appointment_id: appointmentId });
      setBooking(null);
      await load();
    });

  const notify = (m: MissedAppointment) =>
    void act(async () => {
      setNotice(
        sentNotice(await api.post<SendResult>(`/follow-ups/missed-appointments/${m.appointment_id}/notify`, {})),
      );
      await load();
    });

  const onCreate = (e: FormEvent) => {
    e.preventDefault();
    void act(async () => {
      await api.post<FollowUp>("/follow-ups", {
        patient_id: form.patient_id,
        due_date: form.due_date,
        reason: form.reason.trim(),
      });
      setForm({ patient_id: "", due_date: "", reason: FOLLOWUP_REASONS[0] });
      setNotice(t("fuCreated"));
      await load();
    });
  };

  const labels: Record<string, string> = {
    book: "fuBook",
    complete: "fuComplete",
    missed: "fuMarkMissed",
    cancel: "fuCancel",
  };
  const counts: Record<string, number | undefined> = {
    due_today: summary?.due_today,
    overdue: summary?.overdue,
    upcoming: summary?.upcoming,
  };

  return (
    <main className="page">
      <h1 style={{ marginTop: 0 }}>{t("fuTitle")}</h1>
      <p className="muted">
        {t("fuIntro")}
        {can("comms.read") && (
          <>
            {" "}
            <Link href="/communications">{t("navCommunications")}</Link>
          </>
        )}
      </p>
      <Messages error={error} notice={notice} />

      <div className="row" role="tablist" aria-label={t("fuTitle")}>
        {FOLLOWUP_BUCKETS.map((b) => (
          <button
            key={b}
            type="button"
            role="tab"
            aria-selected={bucket === b}
            className={bucket === b ? "primary" : undefined}
            onClick={() => setBucket(b)}
            data-testid={`bucket-${b}`}
          >
            {t(`fuBucket_${b}`)}
            {counts[b] !== undefined ? ` (${counts[b]})` : ""}
          </button>
        ))}
      </div>

      <section className="card" style={{ marginTop: "0.75rem" }}>
        <div className="table-wrap">
          <table data-testid="followup-table">
            <thead>
              <tr>
                <th scope="col">{t("fuPatient")}</th>
                <th scope="col">{t("fuDueDate")}</th>
                <th scope="col">{t("fuReason")}</th>
                <th scope="col">{t("status")}</th>
                <th scope="col">{t("fuAssigned")}</th>
                {(write || sendPerm) && <th scope="col">{t("fuActions")}</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((fu) => (
                <tr key={fu.id}>
                  <td>
                    {fu.patient_name} <span className="tag">{fu.patient_uhid}</span>
                  </td>
                  <td>{fmtDate(`${fu.due_date}T00:00:00`)}</td>
                  <td>{fu.reason}</td>
                  <td>
                    <span className="tag">{t(`fuStatus_${fu.status}`)}</span>
                    {fu.appointment_starts_at && (
                      <span className="muted"> · {fmtDateTime(fu.appointment_starts_at)}</span>
                    )}
                  </td>
                  <td>{fu.assigned_name ?? "—"}</td>
                  {(write || sendPerm) && (
                    <td>
                      <div className="row">
                        {write &&
                          (FOLLOWUP_ACTIONS[fu.status] ?? []).map((a) => (
                            <button
                              key={a}
                              type="button"
                              className={a === "cancel" ? "danger" : undefined}
                              disabled={busy}
                              onClick={() => action(fu, a)}
                            >
                              {t(labels[a])}
                            </button>
                          ))}
                        {sendPerm && ["planned", "reminded", "missed"].includes(fu.status) && (
                          <button type="button" className="ghost" disabled={busy} onClick={() => action(fu, "remind")}>
                            {t("fuRemind")}
                          </button>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted">
                    {t("fuEmpty")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {booking && (
          <div className="card" style={{ marginTop: "0.75rem" }} data-testid="book-panel">
            <h3 style={{ marginTop: 0 }}>
              {t("fuChooseAppointment")} — {booking.fu.patient_name}
            </h3>
            {booking.appts.length === 0 ? (
              <p className="muted">
                {t("fuNoAppointments")} <Link href="/appointments">{t("appointments")}</Link>
              </p>
            ) : (
              <div className="row">
                {booking.appts.map((a) => (
                  <button key={a.id} type="button" disabled={busy} onClick={() => book(a.id)}>
                    {fmtDateTime(a.starts_at)}
                  </button>
                ))}
              </div>
            )}
            <button type="button" className="ghost" onClick={() => setBooking(null)}>
              {t("cancel")}
            </button>
          </div>
        )}
      </section>

      {create && (
        <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="fu-new-h">
          <h2 id="fu-new-h" style={{ marginTop: 0 }}>
            {t("fuNew")}
          </h2>
          <form className="stack" onSubmit={onCreate} style={{ maxWidth: 640 }}>
            <label className="field" htmlFor="fu-patient">
              {t("fuPatient")}
            </label>
            <PatientPicker
              id="fu-patient"
              value={form.patient_id}
              onChange={(id) => setForm({ ...form, patient_id: id })}
            />
            <div className="grid two">
              <label className="field">
                {t("fuDueDate")}
                <input
                  type="date"
                  min={isoDay(new Date())}
                  value={form.due_date}
                  onChange={(e) => setForm({ ...form, due_date: e.target.value })}
                  required
                />
              </label>
              <label className="field">
                {t("fuReason")}
                <input
                  type="text"
                  list="fu-reasons"
                  maxLength={80}
                  value={form.reason}
                  onChange={(e) => setForm({ ...form, reason: e.target.value })}
                  required
                  aria-describedby="fu-reason-hint"
                />
                <datalist id="fu-reasons">
                  {FOLLOWUP_REASONS.map((r) => (
                    <option key={r} value={r} />
                  ))}
                </datalist>
                <span id="fu-reason-hint" className="muted">
                  {t("fuReasonHint")}
                </span>
              </label>
            </div>
            <button type="submit" className="primary" disabled={busy || !form.patient_id || !form.due_date}>
              {t("fuCreate")}
            </button>
          </form>
        </section>
      )}

      <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="missed-h">
        <h2 id="missed-h" style={{ marginTop: 0 }}>
          {t("fuMissedTitle")}
        </h2>
        <p className="muted">{t("fuMissedIntro")}</p>
        <div className="table-wrap">
          <table data-testid="missed-table">
            <thead>
              <tr>
                <th scope="col">{t("fuPatient")}</th>
                <th scope="col">{t("commsWhen")}</th>
                <th scope="col">{t("status")}</th>
                <th scope="col">{t("fuAssigned")}</th>
                {sendPerm && <th scope="col">{t("fuActions")}</th>}
              </tr>
            </thead>
            <tbody>
              {missed.map((m) => (
                <tr key={m.appointment_id}>
                  <td>
                    {m.patient_name} <span className="tag">{m.patient_uhid}</span>
                  </td>
                  <td>{fmtDateTime(m.starts_at)}</td>
                  <td>{m.status}</td>
                  <td>{m.provider_name ?? "—"}</td>
                  {sendPerm && (
                    <td>
                      {m.notified ? (
                        <span className="tag">{t("fuNotified")}</span>
                      ) : (
                        <button type="button" disabled={busy} onClick={() => notify(m)}>
                          {t("fuNotify")}
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
              {missed.length === 0 && (
                <tr>
                  <td colSpan={5} className="muted">
                    {t("fuNoMissed")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

export default function FollowUpsPage() {
  return (
    <AppShell active="followups">
      <FollowUpsBody />
    </AppShell>
  );
}
