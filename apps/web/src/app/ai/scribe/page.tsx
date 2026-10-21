"use client";

/**
 * AI-1 Clinical Scribe: consent → typed/pasted transcript → SOAP DRAFT editor
 * → accept into the open consultation (or discard). No audio is captured or
 * stored; medications are shown verbatim for verification only and are never
 * turned into a prescription.
 */
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { AiFeatureGate, InferenceBadge } from "@/components/AiCommon";
import { Messages, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";

type Encounter = { id: string; patient_id: string; started_at: string; chief_complaint: string };
type Stmt = { text: string; mentions?: string[] };
type Note = { chief_complaint: string; history: string; examination: string; assessment: string; plan: string };
type Session = {
  id: string;
  status: string;
  transcriber_label: string;
  draft: {
    medications_discussed_verbatim: Stmt[];
    unclassified: Stmt[];
    uncertain_or_inaudible: Stmt[];
  } | null;
  draft_valid: boolean | null;
  validation_problems: string[];
  prefill: Note | null;
  inference: string;
  disclaimer: string;
};

const FIELDS: [keyof Note, string][] = [
  ["chief_complaint", "scChief"],
  ["history", "scHistory"],
  ["examination", "scExam"],
  ["assessment", "scAssessment"],
  ["plan", "scPlan"],
];

function ScribeBody() {
  const { t } = useLang();
  const { busy, error, notice, setNotice, act } = useAction();
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [encId, setEncId] = useState("");
  const [consent, setConsent] = useState(false);
  const [noticeLang, setNoticeLang] = useState("en");
  const [session, setSession] = useState<Session | null>(null);
  const [transcript, setTranscript] = useState("");
  const [note, setNote] = useState<Note | null>(null);
  const [reviewed, setReviewed] = useState(false);

  const load = useCallback(async () => {
    const page = await api.get<{ items: Encounter[] }>("/encounters?enc_status=open&limit=50");
    setEncounters(page.items);
    if (page.items[0]) setEncId((cur) => cur || page.items[0].id);
  }, []);

  useEffect(() => {
    void act(load);
  }, [act, load]);

  const start = () =>
    act(async () => {
      setSession(
        await api.post<Session>("/ai/scribe/sessions", {
          encounter_id: encId,
          consent: { patient_verbal_consent: consent, notice_language: noticeLang },
        }),
      );
    });
  const draft = () =>
    act(async () => {
      const s = await api.post<Session>(`/ai/scribe/sessions/${session!.id}/transcript`, { transcript });
      setSession(s);
      setNote(s.prefill);
      setReviewed(false);
    });
  const accept = () =>
    act(async () => {
      setSession(await api.post<Session>(`/ai/scribe/sessions/${session!.id}/accept`, { ...note, reviewed }));
      setNotice(t("scAccepted"));
    });
  const discard = () =>
    act(async () => {
      setSession(await api.post<Session>(`/ai/scribe/sessions/${session!.id}/discard`, {}));
      setNotice(t("scDiscarded"));
    });

  return (
    <>
      <Messages error={error} notice={notice} />
      <p className="notice">{t("scNoAsr")}</p>
      {encounters.length === 0 ? (
        <p className="muted">{t("scNoEncounter")}</p>
      ) : (
        !session && (
          <section className="card stack">
            <label className="field">
              {t("scEncounter")}
              <select value={encId} onChange={(e) => setEncId(e.target.value)}>
                {encounters.map((e) => (
                  <option key={e.id} value={e.id}>
                    {new Date(e.started_at).toLocaleString()} {e.chief_complaint}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              {t("scNoticeLang")}
              <select value={noticeLang} onChange={(e) => setNoticeLang(e.target.value)}>
                <option value="en">English</option>
                <option value="mr">मराठी</option>
                <option value="hi">हिंदी</option>
              </select>
            </label>
            <label>
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />{" "}
              {t("scConsent")}
            </label>
            <button type="button" className="primary" disabled={busy || !consent || !encId} onClick={() => void start()}>
              {t("scStart")}
            </button>
          </section>
        )
      )}
      {session && session.status === "consented" && (
        <section className="card stack" style={{ maxWidth: 760 }}>
          <span className="muted">{session.transcriber_label}</span>
          <label className="field">
            {t("scTranscript")}
            <textarea rows={10} value={transcript} maxLength={30000} onChange={(e) => setTranscript(e.target.value)} />
          </label>
          <button type="button" className="primary" disabled={busy || !transcript.trim()} onClick={() => void draft()}>
            {t("scMakeDraft")}
          </button>
        </section>
      )}
      {session && session.status === "drafted" && note && (
        <section className="card stack" style={{ maxWidth: 760 }} data-testid="scribe-draft">
          <p className="error" role="note" style={{ fontWeight: 600 }}>
            {t("scDraftBanner")}
          </p>
          <InferenceBadge inference={session.inference} />
          {FIELDS.map(([k, label]) => (
            <label key={k} className="field">
              {t(label)}
              <textarea rows={k === "chief_complaint" ? 2 : 4} value={note[k]} onChange={(e) => setNote({ ...note, [k]: e.target.value })} />
            </label>
          ))}
          {session.draft && session.draft.medications_discussed_verbatim.length > 0 && (
            <div className="notice">
              <strong>{t("scMeds")}</strong>
              <ul>
                {session.draft.medications_discussed_verbatim.map((m, i) => (
                  <li key={i}>“{m.text}”</li>
                ))}
              </ul>
            </div>
          )}
          {session.draft && session.draft.unclassified.length + session.draft.uncertain_or_inaudible.length > 0 && (
            <details>
              <summary>{t("scUnclassified")}</summary>
              <ul>
                {[...session.draft.unclassified, ...session.draft.uncertain_or_inaudible].map((m, i) => (
                  <li key={i}>{m.text}</li>
                ))}
              </ul>
            </details>
          )}
          <label>
            <input type="checkbox" checked={reviewed} onChange={(e) => setReviewed(e.target.checked)} /> {t("scReviewed")}
          </label>
          <div className="row">
            <button type="button" className="primary" disabled={busy || !reviewed} onClick={() => void accept()}>
              {t("scAccept")}
            </button>
            <button type="button" className="ghost" disabled={busy} onClick={() => void discard()}>
              {t("scDiscard")}
            </button>
          </div>
        </section>
      )}
      {session && session.draft_valid === false && session.validation_problems.length > 0 && (
        <p className="error">{session.validation_problems.join("; ")}</p>
      )}
    </>
  );
}

export default function ScribePage() {
  const { t } = useLang();
  return (
    <AppShell active="aiScribe">
      <main className="page">
        <h1 style={{ marginTop: 0 }}>{t("scTitle")}</h1>
        <AiFeatureGate feature="ai_scribe">
          <ScribeBody />
        </AiFeatureGate>
      </main>
    </AppShell>
  );
}
