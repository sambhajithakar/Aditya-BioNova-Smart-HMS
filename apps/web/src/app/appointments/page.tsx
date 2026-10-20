"use client";

/**
 * Appointments: day list with filters plus the booking form (patient,
 * branch, slot, reason). Provider conflicts surface as 409 from the API.
 */
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { PatientPicker } from "@/components/PatientPicker";
import { SlotSuggestions } from "@/components/SlotSuggestions";
import Link from "next/link";
import { ApiError, Appointment, Branch, PageOf, Patient, api } from "@/lib/api";
import { t } from "@/lib/i18n";
import { useLang } from "@/lib/lang";
import { useInFlight } from "@/lib/idempotency";
import { defaultBranchId, hasPermission, useMe } from "@/lib/me";

const EMPTY = { patient_id: "", branch_id: "", date: "", time: "", minutes: "30", reason: "" };

function AppointmentsBody() {
  const { lang } = useLang();
  const me = useMe();
  const { busy, run } = useInFlight();
  const [items, setItems] = useState<Appointment[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);


  const load = useCallback(async () => {
    try {
      const [apptPage, patientPage, branchList] = await Promise.all([
        api.get<PageOf<Appointment>>("/appointments?limit=50"),
        api.get<PageOf<Patient>>("/patients?limit=100"), // labels only
        api.get<Branch[]>("/branches"),
      ]);
      setItems(apptPage.items);
      setPatients(patientPage.items);
      setBranches(branchList.filter((b) => b.status === "active"));
      setForm((f) => ({ ...f, branch_id: f.branch_id || defaultBranchId(me, branchList) }));
    } catch {
      setError("Could not load appointments.");
    }
  }, [me]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!form.patient_id) {
      setError(t("pickPatientFirst", lang));
      return;
    }
    setError(null);
    await run(() => book());
  }

  async function book() {
    const startsAt = new Date(`${form.date}T${form.time}:00+05:30`);
    const endsAt = new Date(startsAt.getTime() + Number(form.minutes) * 60_000);
    try {
      await api.post("/appointments", {
        patient_id: form.patient_id,
        branch_id: form.branch_id,
        starts_at: startsAt.toISOString(),
        ends_at: endsAt.toISOString(),
        reason: form.reason,
      });
      setNotice("Appointment booked.");
      setForm({ ...EMPTY, branch_id: form.branch_id });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? String(err.message) : "Booking failed");
    }
  }

  async function cancel(id: string) {
    setError(null);
    try {
      await api.patch(`/appointments/${id}`, { status: "cancelled" });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? String(err.message) : "Cancel failed");
    }
  }

  const nameOf = (id: string) =>
    patients.find((p) => p.id === id)?.full_name ?? "—";

  return (
    <>
      <main className="page">
        <h1 style={{ marginTop: 0 }}>{t("appointments", lang)}</h1>

        <section className="card">
          <h3 style={{ marginTop: 0 }}>{t("createAppointment", lang)}</h3>
          <form onSubmit={onSubmit} style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            <PatientPicker id="apq" value={form.patient_id} onChange={(id) => setForm((f) => ({ ...f, patient_id: id }))} />
            <div className="field">
              <label htmlFor="apb">{t("branch", lang)}</label>
              <select
                id="apb"
                value={form.branch_id}
                onChange={(e) => setForm({ ...form, branch_id: e.target.value })}
              >
                {branches.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="apd">{t("apptDate", lang)}</label>
              <input
                id="apd"
                type="date"
                required
                value={form.date}
                onChange={(e) => setForm({ ...form, date: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="apt">{t("startsAt", lang)}</label>
              <input
                id="apt"
                type="time"
                required
                value={form.time}
                onChange={(e) => setForm({ ...form, time: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="apr">{t("reason", lang)}</label>
              <input
                id="apr"
                value={form.reason}
                onChange={(e) => setForm({ ...form, reason: e.target.value })}
              />
            </div>
            <SlotSuggestions
              branchId={form.branch_id}
              date={form.date}
              onPick={(time, minutes) => setForm((f) => ({ ...f, time, minutes: String(minutes) }))}
            />
            <button className="primary" type="submit" style={{ alignSelf: "end" }} disabled={busy}>
              {t("createAppointment", lang)}
            </button>
          </form>
          {notice && <p className="notice">{notice}</p>}
        </section>

        <section className="card" style={{ marginTop: "1.25rem" }}>
          <table>
            <thead>
              <tr>
                <th>{t("startsAt", lang)}</th>
                <th>{t("patients", lang)}</th>
                <th>{t("reason", lang)}</th>
                <th>{t("status", lang)}</th>
                <th>{t("actions", lang)}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id}>
                  <td>{new Date(a.starts_at).toLocaleString()}</td>
                  <td>{nameOf(a.patient_id)}</td>
                  <td>{a.reason || "—"}</td>
                  <td>{a.status}</td>
                  <td>
                    {a.status === "scheduled" && hasPermission(me, "checkin.manage") && (
                      <Link href={`/checkin/qr?appointment=${a.id}`} style={{ marginRight: "0.5rem" }}>
                        {t("checkinQrLink", lang)}
                      </Link>
                    )}
                    {(a.status === "scheduled" || a.status === "checked_in") && (
                      <button
                        className="secondary"
                        type="button"
                        disabled={busy}
                        onClick={() => void run(() => cancel(a.id))}
                      >
                        {t("cancel", lang)}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr>
                  <td colSpan={5} className="muted">
                    {t("noAppointments", lang)}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </section>

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </main>
    </>
  );
}

export default function AppointmentsPage() {
  return (
    <AppShell active="appointments">
      <AppointmentsBody />
    </AppShell>
  );
}
