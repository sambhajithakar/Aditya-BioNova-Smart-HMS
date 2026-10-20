"use client";

/**
 * Patient communication consent & preferences (comms v2). Per channel
 * opt-in / opt-out with the source it was recorded from; the server enforces
 * "opt-out always wins" (only the patient's own request re-subscribes).
 * Reading needs patient.read; changes need comms.consent.
 */
import { useCallback, useEffect, useState } from "react";
import { Messages, fmtDateTime, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { CHANNELS, CONSENT_SOURCES, PatientComms } from "@/lib/comms";
import { LANGS } from "@/lib/i18n";
import { useLang } from "@/lib/lang";
import { useCan } from "@/lib/me";
import { serverMessage } from "@/lib/saas";

export function PatientCommsPanel({ patientId }: { patientId: string }) {
  const { t } = useLang();
  const can = useCan();
  const write = can("comms.consent");
  const { busy, error, notice, setError, setNotice, act } = useAction();
  const [data, setData] = useState<PatientComms | null>(null);
  const [source, setSource] = useState<string>("patient_request");
  const [lang, setLangPref] = useState("");
  const [email, setEmail] = useState("");

  const load = useCallback(async () => {
    try {
      const d = await api.get<PatientComms>(`/comms/patients/${patientId}`);
      setData(d);
      setLangPref(d.preferred_language ?? "");
      setEmail(d.email ?? "");
    } catch (err) {
      setError(serverMessage(err, t("loadFailed")));
    }
  }, [patientId, setError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const setConsent = (channel: string, status: "opted_in" | "opted_out") =>
    void act(async () => {
      setData(
        await api.put<PatientComms>(`/comms/patients/${patientId}/consent`, { channel, status, source }),
      );
      setNotice(t("pcSaved"));
    });

  const optOutAll = () =>
    void act(async () => {
      setData(await api.post<PatientComms>(`/comms/patients/${patientId}/opt-out`, { source }));
      setNotice(t("pcSaved"));
    });

  const savePrefs = () =>
    void act(async () => {
      setData(
        await api.put<PatientComms>(`/comms/patients/${patientId}/preferences`, {
          preferred_language: lang || null,
          email: email.trim() || null,
        }),
      );
      setNotice(t("pcSaved"));
    });

  if (!data) return <Messages error={error} notice={null} />;
  return (
    <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="pc-h" data-testid="patient-comms">
      <h3 id="pc-h" style={{ marginTop: 0 }}>
        {t("pcTitle")}
      </h3>
      <Messages error={error} notice={notice} />
      <p className="muted" style={{ marginTop: 0 }}>
        {t("pcOptOutWins")}
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">{t("commsChannel")}</th>
              <th scope="col">{t("status")}</th>
              <th scope="col">{t("pcSource")}</th>
              {write && <th scope="col">{t("fuActions")}</th>}
            </tr>
          </thead>
          <tbody>
            {CHANNELS.map((ch) => {
              const c = data.consents.find((x) => x.channel === ch);
              return (
                <tr key={ch}>
                  <td>{t(`channel_${ch}`)}</td>
                  <td>
                    <span className="tag" data-testid={`consent-${ch}`}>
                      {c?.status === "opted_in"
                        ? t("commsOptedIn")
                        : c?.status === "opted_out"
                          ? t("commsOptedOut")
                          : t("pcNoRecord")}
                    </span>
                  </td>
                  <td className="muted">
                    {c?.source ? `${t(`consentSrc_${c.source}`)} · ${fmtDateTime(c.recorded_at)}` : "—"}
                    {c?.actor_name ? ` · ${c.actor_name}` : ""}
                  </td>
                  {write && (
                    <td>
                      <div className="row">
                        <button
                          type="button"
                          disabled={busy || c?.status === "opted_in"}
                          onClick={() => setConsent(ch, "opted_in")}
                        >
                          {t("pcOptIn")}
                        </button>
                        <button
                          type="button"
                          className="danger"
                          disabled={busy || c?.status === "opted_out"}
                          onClick={() => setConsent(ch, "opted_out")}
                        >
                          {t("pcOptOut")}
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {write && (
        <div className="grid two" style={{ marginTop: "0.75rem" }}>
          <label className="field">
            {t("pcSource")}
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              {CONSENT_SOURCES.map((s) => (
                <option key={s} value={s}>
                  {t(`consentSrc_${s}`)}
                </option>
              ))}
            </select>
          </label>
          <div className="row" style={{ alignItems: "flex-end" }}>
            <button type="button" className="danger" disabled={busy} onClick={optOutAll}>
              {t("pcOptOutAll")}
            </button>
          </div>
          <label className="field">
            {t("pcPreferredLanguage")}
            <select value={lang} onChange={(e) => setLangPref(e.target.value)}>
              <option value="">{t("pcClinicDefault")}</option>
              {LANGS.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.native}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            {t("pcEmail")}
            <input type="email" value={email} maxLength={320} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <div className="row">
            <button type="button" className="primary" disabled={busy} onClick={savePrefs}>
              {t("pcSavePrefs")}
            </button>
          </div>
        </div>
      )}
      {data.history.length > 0 && (
        <details style={{ marginTop: "0.75rem" }}>
          <summary>{t("pcHistory")}</summary>
          <ol className="timeline">
            {data.history.map((h, i) => (
              <li key={i} className="muted">
                {fmtDateTime(h.recorded_at)} · {t(`channel_${h.channel}`)} ·{" "}
                {h.status === "opted_in" ? t("commsOptedIn") : t("commsOptedOut")} ·{" "}
                {t(`consentSrc_${h.source}`)}
                {h.actor_name ? ` · ${h.actor_name}` : ""}
              </li>
            ))}
          </ol>
        </details>
      )}
    </section>
  );
}
