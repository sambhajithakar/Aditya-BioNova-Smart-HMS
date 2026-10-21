"use client";

/**
 * Communications (comms v2): mock-outbox banner, this month's quota / spend,
 * consent statistics, "Run reminders now", the template editor with a live
 * preview on synthetic sample values, reminder & cost settings, and the
 * delivery log. Reading needs comms.read; editing comms.manage; running
 * reminders comms.send. The server validates everything shown here.
 */
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Messages, UsageMeter, fmtDateTime, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import {
  ALLOWED_PLACEHOLDERS,
  CHANNELS,
  CommsOverview,
  CommsSettings,
  CommsTemplate,
  DELIVERY_STATUSES,
  DeliveryPage,
  MAX_BODY,
  PURPOSES,
  ReminderRun,
  TEMPLATE_LANGS,
  placeholderProblems,
  renderTemplate,
  smsSegments,
} from "@/lib/comms";
import { LANGS } from "@/lib/i18n";
import { useLang } from "@/lib/lang";
import { useCan } from "@/lib/me";
import { formatPaise, paiseToRupeesInput, parseRupeesToPaise, serverMessage } from "@/lib/saas";

const PAGE = 25;

type Draft = {
  id: string | null;
  channel: string;
  purpose: string;
  language: string;
  name: string;
  subject: string;
  body: string;
  dlt_template_id: string;
  whatsapp_template_name: string;
};

function toDraft(tp: CommsTemplate): Draft {
  return {
    id: tp.id,
    channel: tp.channel,
    purpose: tp.purpose,
    language: tp.language,
    name: tp.name,
    subject: tp.subject,
    body: tp.body,
    dlt_template_id: tp.dlt_template_id ?? "",
    whatsapp_template_name: tp.whatsapp_template_name ?? "",
  };
}

function langName(code: string): string {
  return LANGS.find((l) => l.code === code)?.native ?? code;
}

function CommsBody() {
  const { t } = useLang();
  const can = useCan();
  const manage = can("comms.manage");
  const sendPerm = can("comms.send");
  const { busy, error, notice, setError, setNotice, act } = useAction();
  const [ov, setOv] = useState<CommsOverview | null>(null);
  const [templates, setTemplates] = useState<CommsTemplate[]>([]);
  const [tplFilter, setTplFilter] = useState({ channel: "sms", purpose: "", language: "" });
  const [draft, setDraft] = useState<Draft | null>(null);
  const [settings, setSettings] = useState<CommsSettings | null>(null);
  const [capInput, setCapInput] = useState("");
  const [run, setRun] = useState<ReminderRun | null>(null);
  const [log, setLog] = useState<DeliveryPage | null>(null);
  const [logFilter, setLogFilter] = useState({ channel: "", status: "", purpose: "" });
  const [offset, setOffset] = useState(0);

  const loadOverview = useCallback(async () => {
    const o = await api.get<CommsOverview>("/comms/overview");
    setOv(o);
    setSettings(o.settings);
    setCapInput(paiseToRupeesInput(o.settings.monthly_spend_cap_paise));
  }, []);

  const loadTemplates = useCallback(async () => {
    const q = new URLSearchParams(Object.entries(tplFilter).filter(([, v]) => v));
    setTemplates(await api.get<CommsTemplate[]>(`/comms/templates?${q}`));
  }, [tplFilter]);

  const loadLog = useCallback(async () => {
    const q = new URLSearchParams(Object.entries(logFilter).filter(([, v]) => v));
    q.set("limit", String(PAGE));
    q.set("offset", String(offset));
    setLog(await api.get<DeliveryPage>(`/comms/delivery-log?${q}`));
  }, [logFilter, offset]);

  useEffect(() => {
    loadOverview().catch((err) => setError(serverMessage(err, t("loadFailed"))));
  }, [loadOverview, setError, t]);
  useEffect(() => {
    loadTemplates().catch((err) => setError(serverMessage(err, t("loadFailed"))));
  }, [loadTemplates, setError, t]);
  useEffect(() => {
    loadLog().catch((err) => setError(serverMessage(err, t("loadFailed"))));
  }, [loadLog, setError, t]);

  const allMock = ov ? ov.channels.every((c) => c.mock || !c.live) : true;

  const onRun = () =>
    void act(async () => {
      const r = await api.post<ReminderRun>("/comms/reminders/run", {});
      setRun(r);
      setNotice(t("commsRunDone"));
      await Promise.all([loadOverview(), loadLog()]);
    });

  const problems = useMemo(
    () => (draft ? placeholderProblems(draft.body).concat(placeholderProblems(draft.subject)) : []),
    [draft],
  );

  const saveTemplate = (asNew: boolean) => {
    if (!draft) return;
    void act(async () => {
      const common = {
        name: draft.name.trim(),
        subject: draft.channel === "email" ? draft.subject : "",
        body: draft.body,
        dlt_template_id: draft.channel === "sms" ? draft.dlt_template_id.trim() || null : null,
        whatsapp_template_name:
          draft.channel === "whatsapp" ? draft.whatsapp_template_name.trim() || null : null,
      };
      const saved =
        asNew || !draft.id
          ? await api.post<CommsTemplate>("/comms/templates", {
              ...common,
              channel: draft.channel,
              purpose: draft.purpose,
              language: draft.language,
              is_active: true,
            })
          : await api.patch<CommsTemplate>(`/comms/templates/${draft.id}`, common);
      setDraft(toDraft(saved));
      setNotice(t("commsTemplateSaved"));
      await loadTemplates();
    });
  };

  const onSaveSettings = (e: FormEvent) => {
    e.preventDefault();
    if (!settings) return;
    const cap = parseRupeesToPaise(capInput);
    if (!cap.ok) {
      setError(t("commsCapRupees"));
      return;
    }
    void act(async () => {
      const s = await api.put<CommsSettings>("/comms/settings", {
        monthly_spend_cap_paise: cap.paise,
        quiet_start_hour: settings.quiet_start_hour,
        quiet_end_hour: settings.quiet_end_hour,
        reminder_hours_ahead: settings.reminder_hours_ahead,
        reminder_channels: settings.reminder_channels,
      });
      setSettings(s);
      setNotice(t("commsSettingsSaved"));
      await loadOverview();
    });
  };

  const insert = (name: string) => draft && setDraft({ ...draft, body: `${draft.body}{${name}}` });
  const previewBody = draft ? renderTemplate(draft.body) : "";

  return (
    <main className="page">
      <h1 style={{ marginTop: 0 }}>{t("commsTitle")}</h1>
      <p className="warn-box" role="note" data-testid="mock-outbox-banner">
        <strong>{allMock ? `⚠ ${t("commsMockBanner")}` : t("commsLiveBanner")}</strong>
        {ov && <span className="muted"> ({ov.mock_notice})</span>}
      </p>
      {ov?.in_quiet_hours && <p className="notice">{t("commsQuietNow")}</p>}
      <Messages error={error} notice={notice} />

      {ov && (
        <section className="card" aria-labelledby="usage-h">
          <h2 id="usage-h" style={{ marginTop: 0 }}>
            {t("commsUsageTitle")} · {ov.period}
          </h2>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
            {ov.channels.map((c) => (
              <div key={c.channel}>
                {c.entitled ? (
                  <UsageMeter label={t(`channel_${c.channel}`)} entry={{ limit: c.limit, used: c.used }} />
                ) : (
                  <p className="muted">
                    <strong>{t(`channel_${c.channel}`)}</strong> — {t("commsNotInPlan")}
                  </p>
                )}
                <p className="muted" style={{ margin: "0.25rem 0" }}>
                  {t("commsProvider")}: <span className="tag">{c.provider}</span>
                  {c.mock ? ` · ${t("dstatus_sent_mock")}` : ""}
                </p>
              </div>
            ))}
          </div>
          <p>
            {t("commsSpend")}: <strong>{formatPaise(ov.spend_paise)}</strong> · {t("commsSpendCap")}:{" "}
            {ov.spend_cap_paise === null ? t("commsNoCap") : formatPaise(ov.spend_cap_paise)}
          </p>
          {sendPerm && (
            <button type="button" className="primary" disabled={busy} onClick={onRun} data-testid="run-reminders">
              {t("commsRunReminders")}
            </button>
          )}
          {run && (
            <p className="notice" role="status" data-testid="run-result">
              {t("commsAppointments")}: {run.appointments} · {t("commsFollowUpsShort")}: {run.follow_ups} ·{" "}
              {t("commsSent")}: {run.sent}
              {Object.entries(run.by_status).map(([k, v]) => (
                <span key={k}>
                  {" "}
                  · {t(`dstatus_${k}`)}: {v}
                </span>
              ))}
              <br />
              <span className="muted">{run.mock_notice}</span>
            </p>
          )}
        </section>
      )}

      {ov && (
        <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="consent-h">
          <h2 id="consent-h" style={{ marginTop: 0 }}>
            {t("commsConsentTitle")}
          </h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">{t("commsChannel")}</th>
                  <th scope="col">{t("commsOptedIn")}</th>
                  <th scope="col">{t("commsOptedOut")}</th>
                  <th scope="col">{t("commsUnknown")}</th>
                </tr>
              </thead>
              <tbody>
                {ov.consent.map((c) => (
                  <tr key={c.channel}>
                    <td>{t(`channel_${c.channel}`)}</td>
                    <td>{c.opted_in}</td>
                    <td>{c.opted_out}</td>
                    <td>{c.unknown}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="tpl-h">
        <h2 id="tpl-h" style={{ marginTop: 0 }}>
          {t("commsTemplates")}
        </h2>
        <p className="warn-box" role="note">
          {t("commsTemplateRule")}
        </p>
        <div className="row">
          <label className="field">
            {t("commsChannel")}
            <select
              value={tplFilter.channel}
              onChange={(e) => setTplFilter({ ...tplFilter, channel: e.target.value })}
            >
              <option value="">{t("commsAll")}</option>
              {CHANNELS.map((c) => (
                <option key={c} value={c}>
                  {t(`channel_${c}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            {t("commsPurpose")}
            <select
              value={tplFilter.purpose}
              onChange={(e) => setTplFilter({ ...tplFilter, purpose: e.target.value })}
            >
              <option value="">{t("commsAll")}</option>
              {PURPOSES.map((p) => (
                <option key={p} value={p}>
                  {t(`purpose_${p}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            {t("commsLanguage")}
            <select
              value={tplFilter.language}
              onChange={(e) => setTplFilter({ ...tplFilter, language: e.target.value })}
            >
              <option value="">{t("commsAll")}</option>
              {TEMPLATE_LANGS.map((l) => (
                <option key={l} value={l}>
                  {langName(l)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t("commsName")}</th>
                <th scope="col">{t("commsChannel")}</th>
                <th scope="col">{t("commsPurpose")}</th>
                <th scope="col">{t("commsLanguage")}</th>
              </tr>
            </thead>
            <tbody>
              {templates.map((tp) => (
                <tr key={tp.id} className={draft?.id === tp.id ? "selected" : undefined}>
                  <td>
                    <button type="button" className="ghost" onClick={() => setDraft(toDraft(tp))}>
                      {tp.name}
                    </button>{" "}
                    {tp.is_default && <span className="tag">{t("commsDefaultTag")}</span>}
                  </td>
                  <td>{t(`channel_${tp.channel}`)}</td>
                  <td>{t(`purpose_${tp.purpose}`)}</td>
                  <td>{langName(tp.language)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {draft && (
          <div className="grid two" style={{ marginTop: "1rem" }} data-testid="template-editor">
            <div style={{ display: "grid", gap: "0.75rem" }}>
              <label className="field">
                {t("commsName")}
                <input
                  type="text"
                  value={draft.name}
                  maxLength={120}
                  disabled={!manage}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                />
              </label>
              {draft.channel === "email" && (
                <label className="field">
                  {t("commsSubject")}
                  <input
                    type="text"
                    value={draft.subject}
                    maxLength={200}
                    disabled={!manage}
                    onChange={(e) => setDraft({ ...draft, subject: e.target.value })}
                  />
                </label>
              )}
              <label className="field">
                {t("commsBody")}
                <textarea
                  className="wide"
                  rows={6}
                  maxLength={MAX_BODY[draft.channel as keyof typeof MAX_BODY] ?? 1000}
                  value={draft.body}
                  disabled={!manage}
                  onChange={(e) => setDraft({ ...draft, body: e.target.value })}
                  data-testid="template-body"
                />
              </label>
              {manage && (
                <div className="row" aria-label={t("commsInsert")}>
                  {ALLOWED_PLACEHOLDERS.map((p) => (
                    <button key={p} type="button" className="ghost" onClick={() => insert(p)}>
                      {`{${p}}`}
                    </button>
                  ))}
                </div>
              )}
              {draft.channel === "sms" && (
                <label className="field">
                  {t("commsDltId")}
                  <input
                    type="text"
                    inputMode="numeric"
                    value={draft.dlt_template_id}
                    maxLength={30}
                    disabled={!manage}
                    onChange={(e) => setDraft({ ...draft, dlt_template_id: e.target.value })}
                  />
                </label>
              )}
              {draft.channel === "whatsapp" && (
                <label className="field">
                  {t("commsWaName")}
                  <input
                    type="text"
                    value={draft.whatsapp_template_name}
                    maxLength={120}
                    disabled={!manage}
                    onChange={(e) => setDraft({ ...draft, whatsapp_template_name: e.target.value })}
                  />
                </label>
              )}
              {problems.length > 0 && (
                <ul className="field-error" data-testid="template-problems">
                  {problems.map((p, i) => (
                    <li key={i}>
                      {p.kind === "disallowed"
                        ? `{${p.name}} — ${t("commsErrDisallowed")}`
                        : p.kind === "unknown"
                          ? `{${p.name}} — ${t("commsErrUnknown")}`
                          : t("commsErrBraces")}
                    </li>
                  ))}
                </ul>
              )}
              {manage && (
                <div className="row">
                  {draft.id && (
                    <button
                      type="button"
                      className="primary"
                      disabled={busy || problems.length > 0}
                      onClick={() => saveTemplate(false)}
                    >
                      {t("commsSaveTemplate")}
                    </button>
                  )}
                  <button type="button" disabled={busy || problems.length > 0} onClick={() => saveTemplate(true)}>
                    {t("commsSaveAsNew")}
                  </button>
                </div>
              )}
            </div>
            <div>
              <h3 style={{ marginTop: 0 }}>{t("commsPreview")}</h3>
              {draft.channel === "email" && <p style={{ fontWeight: 600 }}>{renderTemplate(draft.subject)}</p>}
              <p className="card" style={{ whiteSpace: "pre-wrap" }} data-testid="template-preview">
                {previewBody}
              </p>
              <p className="muted">
                {previewBody.length} {t("commsChars")}
                {draft.channel === "sms" && ` · ${smsSegments(previewBody)} ${t("commsSegments")}`} ·{" "}
                {t("commsPreviewNote")}
              </p>
            </div>
          </div>
        )}
      </section>

      {settings && (
        <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="set-h">
          <h2 id="set-h" style={{ marginTop: 0 }}>
            {t("commsSettings")}
          </h2>
          <form className="stack" onSubmit={onSaveSettings} style={{ maxWidth: 640 }}>
            <fieldset disabled={!manage} style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className="muted">{t("commsQuietHours")}</legend>
              <div className="grid two">
                <label className="field">
                  {t("commsQuietFrom")}
                  <input
                    type="number"
                    min={0}
                    max={23}
                    value={settings.quiet_start_hour}
                    onChange={(e) => setSettings({ ...settings, quiet_start_hour: Number(e.target.value) })}
                  />
                </label>
                <label className="field">
                  {t("commsQuietTo")}
                  <input
                    type="number"
                    min={0}
                    max={23}
                    value={settings.quiet_end_hour}
                    onChange={(e) => setSettings({ ...settings, quiet_end_hour: Number(e.target.value) })}
                  />
                </label>
              </div>
              <label className="field">
                {t("commsHoursAhead")}
                <input
                  type="number"
                  min={1}
                  max={168}
                  value={settings.reminder_hours_ahead}
                  onChange={(e) => setSettings({ ...settings, reminder_hours_ahead: Number(e.target.value) })}
                />
              </label>
              <fieldset style={{ border: 0, padding: 0 }}>
                <legend>{t("commsReminderChannels")}</legend>
                <div className="row">
                  {CHANNELS.map((c) => (
                    <label key={c}>
                      <input
                        type="checkbox"
                        checked={settings.reminder_channels.includes(c)}
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            reminder_channels: e.target.checked
                              ? [...settings.reminder_channels, c]
                              : settings.reminder_channels.filter((x) => x !== c),
                          })
                        }
                      />{" "}
                      {t(`channel_${c}`)}
                    </label>
                  ))}
                </div>
              </fieldset>
              <label className="field">
                {t("commsCapRupees")}
                <input type="text" inputMode="decimal" value={capInput} onChange={(e) => setCapInput(e.target.value)} />
              </label>
              {manage && (
                <button type="submit" className="primary" disabled={busy}>
                  {t("commsSaveSettings")}
                </button>
              )}
            </fieldset>
          </form>
        </section>
      )}

      <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="log-h">
        <h2 id="log-h" style={{ marginTop: 0 }}>
          {t("commsDeliveryLog")}
        </h2>
        <div className="row">
          <label className="field">
            {t("commsChannel")}
            <select
              value={logFilter.channel}
              onChange={(e) => {
                setOffset(0);
                setLogFilter({ ...logFilter, channel: e.target.value });
              }}
            >
              <option value="">{t("commsAll")}</option>
              {CHANNELS.map((c) => (
                <option key={c} value={c}>
                  {t(`channel_${c}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            {t("status")}
            <select
              value={logFilter.status}
              onChange={(e) => {
                setOffset(0);
                setLogFilter({ ...logFilter, status: e.target.value });
              }}
            >
              <option value="">{t("commsAll")}</option>
              {DELIVERY_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {t(`dstatus_${s}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            {t("commsPurpose")}
            <select
              value={logFilter.purpose}
              onChange={(e) => {
                setOffset(0);
                setLogFilter({ ...logFilter, purpose: e.target.value });
              }}
            >
              <option value="">{t("commsAll")}</option>
              {PURPOSES.map((p) => (
                <option key={p} value={p}>
                  {t(`purpose_${p}`)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="table-wrap">
          <table data-testid="delivery-log">
            <thead>
              <tr>
                <th scope="col">{t("commsWhen")}</th>
                <th scope="col">{t("commsChannel")}</th>
                <th scope="col">{t("commsPurpose")}</th>
                <th scope="col">{t("commsRecipient")}</th>
                <th scope="col">{t("status")}</th>
                <th scope="col">{t("commsProvider")}</th>
                <th scope="col">{t("commsCost")}</th>
              </tr>
            </thead>
            <tbody>
              {log?.items.map((d) => (
                <tr key={d.id}>
                  <td>{fmtDateTime(d.created_at)}</td>
                  <td>{t(`channel_${d.channel}`)}</td>
                  <td>{t(`purpose_${d.purpose}`)}</td>
                  <td>{d.recipient_masked ?? "—"}</td>
                  <td>
                    <span className="tag" title={d.error ?? undefined}>
                      {t(`dstatus_${d.status}`)}
                    </span>
                  </td>
                  <td>{d.provider}</td>
                  <td>{formatPaise(d.cost_paise)}</td>
                </tr>
              ))}
              {log && log.items.length === 0 && (
                <tr>
                  <td colSpan={7} className="muted">
                    {t("commsNoDeliveries")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {log && log.total > PAGE && (
          <div className="pager">
            <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
              {t("commsPrev")}
            </button>
            <span className="muted">
              {offset + 1}–{Math.min(offset + PAGE, log.total)} / {log.total}
            </span>
            <button
              type="button"
              disabled={offset + PAGE >= log.total}
              onClick={() => setOffset(offset + PAGE)}
            >
              {t("commsNext")}
            </button>
          </div>
        )}
      </section>
    </main>
  );
}

export default function CommunicationsPage() {
  return (
    <AppShell active="communications">
      <CommsBody />
    </AppShell>
  );
}
