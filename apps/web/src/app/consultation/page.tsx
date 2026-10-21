"use client";

/**
 * Doctor's consultation workspace: open an encounter from the queue, record
 * vitals + structured diagnosis, build a prescription with explicit
 * per-item dose / route / frequency / duration (no silent defaults), check
 * the server's allergy/duplicate safety gate, sign, then close the
 * encounter.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { DeviceReadingsPanel } from "@/components/DeviceReadings";
import { AppShell } from "@/components/AppShell";
import { PatientPicker, patientLabel } from "@/components/PatientPicker";
import {
  ApiError,
  Branch,
  Drug,
  Encounter,
  EncounterDetail,
  PageOf,
  Patient,
  PrescriptionDetail,
  QueueEntry,
  RxWarnings,
  api,
} from "@/lib/api";
import { useLang } from "@/lib/lang";
import { NeedsConnection, useOnline } from "@/components/device/online";
import { defaultBranchId, useCan, useMe } from "@/lib/me";
import { useInFlight } from "@/lib/idempotency";
import { hasFeature } from "@/lib/saas";
import {
  FREQUENCIES,
  ROUTES,
  RxDraftItem,
  RxField,
  emptyRxItem,
  isRxItemValid,
  toRxItemIn,
  validateRxItem,
} from "@/lib/rx";

const EMPTY_VITALS = {
  bp_systolic: "",
  bp_diastolic: "",
  pulse: "",
  temperature_c: "",
  spo2: "",
  weight_kg: "",
};

function errMsg(err: unknown, fallback: string): string {
  return err instanceof ApiError ? String(err.message) : fallback;
}

export default function ConsultationPage() {
  return (
    <AppShell active="consultation">
      <Consultation />
    </AppShell>
  );
}

function Consultation() {
  const { t } = useLang();
  const me = useMe();
  const can = useCan();
  const online = useOnline(); // signing is server-finalised: never offline
  const { busy, run } = useInFlight();
  const [branches, setBranches] = useState<Branch[]>([]);
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [openList, setOpenList] = useState<Encounter[]>([]);
  const [open, setOpen] = useState<EncounterDetail | null>(null);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [drugs, setDrugs] = useState<Drug[]>([]);
  const [drugQuery, setDrugQuery] = useState("");
  const [vitals, setVitals] = useState(EMPTY_VITALS);
  const [dx, setDx] = useState({ code: "", label: "" });
  const [items, setItems] = useState<RxDraftItem[]>([]);
  const [showErrors, setShowErrors] = useState(false);
  const [rxDraft, setRxDraft] = useState({ diagnosis_text: "", advice: "", follow_up: "" });
  const [draftRxId, setDraftRxId] = useState<string | null>(null);
  const [signedRx, setSignedRx] = useState<PrescriptionDetail | null>(null);
  const [warnings, setWarnings] = useState<RxWarnings | null>(null);
  const [ackAllergies, setAckAllergies] = useState(false);
  const [pickPatient, setPickPatient] = useState("");
  const [pickQueue, setPickQueue] = useState("");
  const [chiefComplaint, setChiefComplaint] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const openEncounter = useCallback(async (id: string) => {
    const detail = await api.get<EncounterDetail>(`/encounters/${id}`);
    setOpen(detail);
    try {
      setPatient(await api.get<Patient>(`/patients/${detail.patient_id}`));
    } catch {
      setPatient(null);
    }
  }, []);

  const load = useCallback(async () => {
    try {
      const [branchList, queuePage, encounterPage] = await Promise.all([
        api.get<Branch[]>("/branches"),
        api.get<PageOf<QueueEntry>>("/opd/queue?limit=100"),
        // H6: the API filter is `enc_status`, not `status`.
        api.get<PageOf<Encounter>>("/encounters?enc_status=open&limit=20"),
      ]);
      setBranches(branchList.filter((b) => b.status === "active"));
      setQueue(
        queuePage.items.filter((e) => ["waiting", "called", "in_consultation"].includes(e.status)),
      );
      setOpenList(encounterPage.items);
      return encounterPage.items;
    } catch {
      setError(t("loadFailed"));
      return [];
    }
  }, [t]);

  // Initial load: resume this doctor's own open encounter if there is one.
  useEffect(() => {
    void load().then((list) => {
      const mine = list.find((e) => e.provider_user_id === me?.user.id) ?? null;
      if (mine) void openEncounter(mine.id);
    });
  }, [load, openEncounter, me?.user.id]);

  // Drug search is independent of the workspace (D4).
  useEffect(() => {
    const h = setTimeout(() => {
      api
        .get<Drug[]>(`/prescriptions/drugs?limit=20&q=${encodeURIComponent(drugQuery)}`)
        .then(setDrugs)
        .catch(() => setDrugs([]));
    }, 200);
    return () => clearTimeout(h);
  }, [drugQuery]);

  const editable = open?.status === "open";

  function updateItem(key: string, field: RxField, value: string) {
    setItems((xs) => xs.map((x) => (x.key === key ? { ...x, [field]: value } : x)));
    setDraftRxId(null); // edits invalidate any draft created for the safety check
    setWarnings(null);
  }

  const itemErrors = useMemo(
    () => Object.fromEntries(items.map((it) => [it.key, validateRxItem(it)])),
    [items],
  );
  const allValid = items.length > 0 && items.every(isRxItemValid);

  async function startEncounter() {
    if (!pickPatient) return setError(t("pickPatientFirst"));
    setError(null);
    await run(async () => {
      try {
        const enc = await api.post<Encounter>("/encounters", {
          patient_id: pickPatient,
          branch_id: defaultBranchId(me, branches),
          chief_complaint: chiefComplaint,
          queue_entry_id: pickQueue || undefined,
        });
        setNotice(t("encounterStarted"));
        setChiefComplaint("");
        setPickQueue("");
        setPickPatient("");
        await load();
        await openEncounter(enc.id);
      } catch (err) {
        setError(errMsg(err, t("actionFailed")));
      }
    });
  }

  async function saveVitals() {
    if (!open) return;
    setError(null);
    await run(async () => {
      try {
        const body: Record<string, unknown> = {};
        for (const [k, v] of Object.entries(vitals)) {
          if (v !== "") body[k] = Number(v);
        }
        await api.post(`/encounters/${open.id}/vitals`, body);
        setVitals(EMPTY_VITALS);
        setNotice(t("recordVitals"));
        await openEncounter(open.id);
      } catch (err) {
        setError(errMsg(err, t("actionFailed")));
      }
    });
  }

  async function saveDiagnosis() {
    if (!open || !dx.code || !dx.label) return;
    setError(null);
    await run(async () => {
      try {
        await api.post(`/encounters/${open.id}/diagnoses`, {
          code: dx.code,
          label: dx.label,
          kind: "primary",
        });
        setDx({ code: "", label: "" });
        await openEncounter(open.id);
      } catch (err) {
        setError(errMsg(err, t("actionFailed")));
      }
    });
  }

  async function closeEncounter() {
    if (!open) return;
    setError(null);
    await run(async () => {
      try {
        await api.post(`/encounters/${open.id}/complete`, {});
        setNotice(t("encounterClosed"));
        await openEncounter(open.id);
        await load();
      } catch (err) {
        setError(errMsg(err, t("actionFailed")));
      }
    });
  }

  function finishSign(signed: PrescriptionDetail) {
    setSignedRx(signed);
    setWarnings(null);
    setAckAllergies(false);
    setDraftRxId(null);
    setItems([]);
    setShowErrors(false);
    setRxDraft({ diagnosis_text: "", advice: "", follow_up: "" });
    setNotice(`${t("signed")} v${signed.version}`);
    if (open) void openEncounter(open.id);
  }

  async function signPrescription(acknowledge: boolean) {
    if (!open) return;
    setShowErrors(true);
    if (!allValid) return setError(t("rxFixErrors"));
    setError(null);
    await run(async () => {
      try {
        // D5: create the draft once; retries after a warning reuse it.
        let id = draftRxId;
        if (!id) {
          const draft = await api.post<PrescriptionDetail>("/prescriptions", {
            patient_id: open.patient_id,
            encounter_id: open.id,
            ...rxDraft,
            items: items.map(toRxItemIn),
          });
          id = draft.id;
          setDraftRxId(id);
        }
        if (!acknowledge) {
          const w = await api.post<RxWarnings>(`/prescriptions/${id}/warnings`, {});
          if (w.warnings.length > 0) setWarnings(w);
          if (w.blocking) return;
        }
        const signed = await api.post<PrescriptionDetail>(`/prescriptions/${id}/sign`, {
          acknowledge_allergies: acknowledge,
        });
        finishSign(signed);
      } catch (err) {
        setError(errMsg(err, t("actionFailed")));
      }
    });
  }

  const canWrite = can("encounter.write");
  const canSign = can("prescription.sign");

  return (
    <main className="page">
      <h1 style={{ marginTop: 0 }}>{t("consultation")}</h1>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="notice" aria-live="polite">
          {notice}
        </p>
      )}

      {openList.length > 0 && (
        <section className="card">
          <div className="field">
            <label htmlFor="enc-open">{t("openEncounters")}</label>
            <select
              id="enc-open"
              value={open?.id ?? ""}
              onChange={(e) => {
                setSignedRx(null);
                setItems([]);
                setDraftRxId(null);
                if (e.target.value) void openEncounter(e.target.value);
                else {
                  setOpen(null);
                  setPatient(null);
                }
              }}
            >
              <option value="">— {t("startEncounter")} —</option>
              {openList.map((e) => (
                <option key={e.id} value={e.id}>
                  {new Date(e.started_at).toLocaleString()} — {e.chief_complaint || e.patient_id.slice(0, 8)}
                </option>
              ))}
            </select>
          </div>
        </section>
      )}

      {!open && canWrite && (
        <section className="card" style={{ marginTop: "1rem" }}>
          <h3 style={{ marginTop: 0 }}>{t("startEncounter")}</h3>
          <div className="row">
            <PatientPicker
              id="cp"
              value={pickPatient}
              onChange={(id) => setPickPatient(id)}
              showAllergies
            />
            <div className="field">
              <label htmlFor="cq">{t("token")}</label>
              <select id="cq" value={pickQueue} onChange={(e) => setPickQueue(e.target.value)}>
                <option value="">—</option>
                {queue
                  .filter((q) => !pickPatient || q.patient_id === pickPatient)
                  .map((q) => (
                    <option key={q.id} value={q.id}>
                      #{q.token_number} ({t(q.status)})
                    </option>
                  ))}
              </select>
            </div>
            <div className="field grow">
              <label htmlFor="cc">{t("chiefComplaint")}</label>
              <input
                id="cc"
                value={chiefComplaint}
                onChange={(e) => setChiefComplaint(e.target.value)}
              />
            </div>
            <button
              className="primary"
              type="button"
              style={{ alignSelf: "end" }}
              disabled={busy}
              onClick={() => void startEncounter()}
            >
              {t("startEncounter")}
            </button>
          </div>
        </section>
      )}

      {open && (
        <>
          <section className="card" style={{ marginTop: "1rem" }}>
            <h3 style={{ marginTop: 0 }} data-testid="encounter-patient">
              {patient ? patientLabel(patient) : t("loading")}
              {open.status === "completed" && (
                <span className="tag" style={{ marginLeft: "0.5rem" }}>
                  {t("encounterClosed")}
                </span>
              )}
            </h3>
            {patient?.allergies && (
              <p className="error">
                ⚠ {t("allergies")}: {patient.allergies}
              </p>
            )}
            <p className="muted">
              {t("chiefComplaint")}: {open.chief_complaint || "—"}
            </p>
            <div className="row">
              {editable && canWrite && (
                <button
                  className="secondary"
                  type="button"
                  disabled={busy}
                  onClick={() => void closeEncounter()}
                >
                  {t("closeEncounter")}
                </button>
              )}
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setOpen(null);
                  setPatient(null);
                  setSignedRx(null);
                  setItems([]);
                }}
              >
                {t("newConsultation")}
              </button>
            </div>
          </section>

          <div className="grid two" style={{ marginTop: "1rem" }}>
            <section className="card">
              <h3 style={{ marginTop: 0 }}>{t("vitals")}</h3>
              <div style={{ display: "grid", gap: "0.5rem" }}>
                {(
                  [
                    ["bp_systolic", t("bpSystolic")],
                    ["bp_diastolic", t("bpDiastolic")],
                    ["pulse", t("pulse")],
                    ["temperature_c", t("temp")],
                    ["spo2", t("spo2")],
                    ["weight_kg", t("weight")],
                  ] as const
                ).map(([key, label]) => (
                  <div className="field" key={key}>
                    <label htmlFor={`v-${key}`}>{label}</label>
                    <input
                      id={`v-${key}`}
                      inputMode="decimal"
                      value={vitals[key]}
                      disabled={!editable || !canWrite}
                      onChange={(e) => setVitals((v) => ({ ...v, [key]: e.target.value }))}
                    />
                  </div>
                ))}
                <button
                  type="button"
                  className="secondary"
                  disabled={!editable || !canWrite || busy}
                  onClick={() => void saveVitals()}
                >
                  {t("recordVitals")}
                </button>
              </div>
              {open.vitals.length > 0 && (
                <div className="table-wrap">
                  <table style={{ marginTop: "0.75rem" }}>
                    <thead>
                      <tr>
                        <th scope="col">{t("bpShort")}</th>
                        <th scope="col">{t("pulse")}</th>
                        <th scope="col">{t("spo2")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {open.vitals.slice(-3).map((v) => (
                        <tr key={v.id}>
                          <td>
                            {v.bp_systolic ?? "—"}/{v.bp_diastolic ?? "—"}
                          </td>
                          <td>{v.pulse ?? "—"}</td>
                          <td>{v.spo2 ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {hasFeature(me, "medical_devices") &&
                (can("device.review") || can("device.capture")) && (
                  <DeviceReadingsPanel
                    key={open.id}
                    encounterId={open.id}
                    patientLabel={patient ? `${patient.full_name} (${patient.uhid})` : ""}
                    canReview={editable && online && can("device.review") && canWrite}
                    onAccepted={() => void openEncounter(open.id)}
                  />
                )}
            </section>

            <section className="card">
              <h3 style={{ marginTop: 0 }}>{t("diagnosis")}</h3>
              <div className="field">
                <label htmlFor="dx-code">{t("dxCode")}</label>
                <input
                  id="dx-code"
                  value={dx.code}
                  disabled={!editable || !canWrite}
                  onChange={(e) => setDx((d) => ({ ...d, code: e.target.value }))}
                  placeholder="J06.9"
                />
              </div>
              <div className="field">
                <label htmlFor="dx-label">{t("dxLabel")}</label>
                <input
                  id="dx-label"
                  value={dx.label}
                  disabled={!editable || !canWrite}
                  onChange={(e) => setDx((d) => ({ ...d, label: e.target.value }))}
                />
              </div>
              <button
                type="button"
                className="secondary"
                disabled={!editable || !canWrite || busy}
                onClick={() => void saveDiagnosis()}
              >
                {t("addDiagnosis")}
              </button>
              <ul>
                {open.diagnoses.map((d) => (
                  <li key={d.id}>
                    <code>{d.code}</code> {d.label} <span className="muted">({d.kind})</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>

          {canSign && (
            <section className="card" style={{ marginTop: "1.25rem" }}>
              <h3 style={{ marginTop: 0 }}>{t("prescribe")}</h3>

              <div className="field">
                <label htmlFor="drug-q">{t("drugSearch")}</label>
                <input
                  id="drug-q"
                  type="search"
                  value={drugQuery}
                  onChange={(e) => setDrugQuery(e.target.value)}
                  placeholder={t("drugSearch")}
                />
              </div>
              <div className="row" style={{ marginTop: "0.5rem" }}>
                {drugs.slice(0, 8).map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    className="chip"
                    disabled={!editable}
                    onClick={() => {
                      setItems((xs) => [...xs, emptyRxItem(d)]);
                      setDraftRxId(null);
                    }}
                  >
                    + {d.generic_name}
                  </button>
                ))}
              </div>

              <datalist id="freq-list">
                {FREQUENCIES.map((f) => (
                  <option key={f} value={f} />
                ))}
              </datalist>

              {items.map((it, idx) => {
                const errs = showErrors ? itemErrors[it.key] ?? {} : {};
                const fieldProps = (f: RxField) => ({
                  id: `rx-${idx}-${f}`,
                  "aria-invalid": errs[f] ? true : undefined,
                  "aria-describedby": errs[f] ? `rx-${idx}-${f}-err` : undefined,
                });
                const errEl = (f: RxField) =>
                  errs[f] ? (
                    <span className="field-error" id={`rx-${idx}-${f}-err`}>
                      {t(errs[f]!)}
                    </span>
                  ) : null;
                return (
                  <fieldset className="rx-item" key={it.key} data-testid="rx-item">
                    <legend>
                      {idx + 1}. <strong>{it.drug_name}</strong>
                      <button
                        type="button"
                        className="icon"
                        aria-label={`${t("remove")} ${it.drug_name}`}
                        onClick={() => {
                          setItems((xs) => xs.filter((x) => x.key !== it.key));
                          setDraftRxId(null);
                        }}
                      >
                        ✕
                      </button>
                    </legend>
                    <div className="rx-grid">
                      <div className="field">
                        <label htmlFor={`rx-${idx}-dose`}>{t("dose")} *</label>
                        <input
                          {...fieldProps("dose")}
                          value={it.dose}
                          placeholder={t("dosePlaceholder")}
                          maxLength={100}
                          onChange={(e) => updateItem(it.key, "dose", e.target.value)}
                        />
                        {errEl("dose")}
                      </div>
                      <div className="field">
                        <label htmlFor={`rx-${idx}-route`}>{t("route")} *</label>
                        <select
                          {...fieldProps("route")}
                          value={it.route}
                          onChange={(e) => updateItem(it.key, "route", e.target.value)}
                        >
                          <option value="">—</option>
                          {ROUTES.map((r) => (
                            <option key={r} value={r}>
                              {t(`route_${r}`)}
                            </option>
                          ))}
                        </select>
                        {errEl("route")}
                      </div>
                      <div className="field">
                        <label htmlFor={`rx-${idx}-frequency`}>{t("frequency")} *</label>
                        <input
                          {...fieldProps("frequency")}
                          list="freq-list"
                          value={it.frequency}
                          maxLength={100}
                          placeholder="OD / BD / TDS…"
                          onChange={(e) => updateItem(it.key, "frequency", e.target.value)}
                        />
                        {errEl("frequency")}
                      </div>
                      <div className="field">
                        <label htmlFor={`rx-${idx}-duration_days`}>{t("duration")} *</label>
                        <input
                          {...fieldProps("duration_days")}
                          inputMode="numeric"
                          value={it.duration_days}
                          onChange={(e) => updateItem(it.key, "duration_days", e.target.value)}
                        />
                        {errEl("duration_days")}
                      </div>
                      <div className="field">
                        <label htmlFor={`rx-${idx}-quantity`}>{t("quantityText")}</label>
                        <input
                          {...fieldProps("quantity")}
                          value={it.quantity}
                          maxLength={100}
                          onChange={(e) => updateItem(it.key, "quantity", e.target.value)}
                        />
                        {errEl("quantity")}
                      </div>
                      <div className="field">
                        <label htmlFor={`rx-${idx}-dispense_quantity`}>{t("dispenseQty")}</label>
                        <input
                          {...fieldProps("dispense_quantity")}
                          inputMode="numeric"
                          value={it.dispense_quantity}
                          onChange={(e) => updateItem(it.key, "dispense_quantity", e.target.value)}
                        />
                        {errEl("dispense_quantity")}
                      </div>
                      <div className="field span-all">
                        <label htmlFor={`rx-${idx}-instructions`}>{t("instructions")}</label>
                        <input
                          {...fieldProps("instructions")}
                          value={it.instructions}
                          maxLength={500}
                          onChange={(e) => updateItem(it.key, "instructions", e.target.value)}
                        />
                        {errEl("instructions")}
                      </div>
                    </div>
                  </fieldset>
                );
              })}

              <div className="field" style={{ marginTop: "0.75rem" }}>
                <label htmlFor="rx-dx">{t("diagnosis")}</label>
                <input
                  id="rx-dx"
                  value={rxDraft.diagnosis_text}
                  onChange={(e) => {
                    setRxDraft((r) => ({ ...r, diagnosis_text: e.target.value }));
                    setDraftRxId(null);
                  }}
                />
              </div>
              <div className="field">
                <label htmlFor="rx-advice">{t("advice")}</label>
                <input
                  id="rx-advice"
                  value={rxDraft.advice}
                  onChange={(e) => {
                    setRxDraft((r) => ({ ...r, advice: e.target.value }));
                    setDraftRxId(null);
                  }}
                />
              </div>
              <div className="field">
                <label htmlFor="rx-follow">{t("followUps")}</label>
                <input
                  id="rx-follow"
                  value={rxDraft.follow_up}
                  onChange={(e) => {
                    setRxDraft((r) => ({ ...r, follow_up: e.target.value }));
                    setDraftRxId(null);
                  }}
                />
              </div>

              <NeedsConnection />
              <button
                className="primary"
                type="button"
                style={{ marginTop: "0.75rem" }}
                disabled={items.length === 0 || !editable || busy || !online}
                onClick={() => void signPrescription(false)}
              >
                {t("signRx")}
              </button>
            </section>
          )}

          {warnings && warnings.warnings.length > 0 && (
            <section className="card error" role="alert" style={{ marginTop: "1rem" }}>
              <h3 style={{ marginTop: 0 }}>{t("signWarningTitle")}</h3>
              <ul>
                {warnings.warnings.map((w, i) => (
                  <li key={i}>{w.message}</li>
                ))}
              </ul>
              {warnings.blocking && (
                <>
                  <label style={{ display: "block", marginBottom: "0.5rem" }}>
                    <input
                      type="checkbox"
                      checked={ackAllergies}
                      onChange={(e) => setAckAllergies(e.target.checked)}
                    />{" "}
                    {t("acknowledgeAllergies")}
                  </label>
                  <button
                    className="primary"
                    type="button"
                    disabled={!ackAllergies || busy || !online}
                    onClick={() => void signPrescription(true)}
                  >
                    {t("signRx")}
                  </button>
                </>
              )}
            </section>
          )}

          {signedRx && (
            <p className="notice" style={{ marginTop: "1rem" }}>
              {t("signed")} v{signedRx.version} —{" "}
              <a href={`/print/rx/${signedRx.id}`} target="_blank" rel="noopener noreferrer">
                {t("printRx")}
              </a>
            </p>
          )}

          {open.prescription_ids.length > 0 && (
            <section className="card" style={{ marginTop: "1.25rem" }}>
              <h3 style={{ marginTop: 0 }}>{t("prescriptions")}</h3>
              <ul>
                {open.prescription_ids.map((id) => (
                  <li key={id}>
                    <a href={`/print/rx/${id}`} target="_blank" rel="noopener noreferrer">
                      {t("printRx")}
                    </a>{" "}
                    <code className="muted">{id.slice(0, 8)}</code>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </main>
  );
}
