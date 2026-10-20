"use client";

/**
 * AI-1 knowledge assistant: upload approved SOPs / manuals / policies (text or
 * Markdown; documents with patient data are refused), approve them, and ask
 * questions answered with quoted passages + citations. Mock inference is
 * labelled. Answers are rendered as plain text only (no links/HTML).
 */
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { AiFeatureGate, InferenceBadge } from "@/components/AiCommon";
import { Messages, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { useCan } from "@/lib/me";

type Citation = { chunk_id: string; document_title: string; section: string; version: number; score: number };
type Answer = {
  answered: boolean;
  answer: { text: string; citation: Citation }[];
  refusal: string | null;
  retrieved: Citation[];
  inference: string;
  method: string;
  note: string | null;
};
type Doc = {
  id: string;
  title: string;
  doc_type: string;
  version: number;
  status: string;
  visibility_roles: string[];
  injection_flags: number;
};

function KnowledgeBody() {
  const { t } = useLang();
  const can = useCan();
  const manage = can("ai.knowledge.manage");
  const { busy, error, notice, act } = useAction();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [title, setTitle] = useState("");
  const [docType, setDocType] = useState("sop");
  const [text, setText] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [roles, setRoles] = useState("");
  const [noPhi, setNoPhi] = useState(false);
  const [hasPhi, setHasPhi] = useState(false);

  const loadDocs = useCallback(async () => {
    setDocs(await api.get<Doc[]>("/ai/knowledge/documents"));
  }, []);

  useEffect(() => {
    void act(loadDocs);
  }, [act, loadDocs]);

  async function ask(e: FormEvent) {
    e.preventDefault();
    await act(async () => setAnswer(await api.post<Answer>("/ai/knowledge/ask", { question })));
  }

  async function upload(e: FormEvent) {
    e.preventDefault();
    await act(async () => {
      await api.post("/ai/knowledge/documents", {
        title,
        doc_type: docType,
        text,
        file_name: fileName,
        contains_patient_data: hasPhi,
        visibility_roles: roles
          .split(",")
          .map((r) => r.trim())
          .filter(Boolean),
      });
      setTitle("");
      setText("");
      setNoPhi(false);
      await loadDocs();
    });
  }

  async function transition(id: string, to: "approve" | "archive") {
    await act(async () => {
      await api.post(`/ai/knowledge/documents/${id}/${to}`, {});
      await loadDocs();
    });
  }

  return (
    <>
      <Messages error={error} notice={notice} />
      <section className="card">
        <form className="stack" onSubmit={(e) => void ask(e)}>
          <label className="field">
            {t("kbQuestion")}
            <input value={question} maxLength={500} onChange={(e) => setQuestion(e.target.value)} required />
          </label>
          <button type="submit" className="primary" disabled={busy}>
            {t("kbAsk")}
          </button>
        </form>
      </section>
      {answer && (
        <section className="card" style={{ marginTop: "1rem" }} data-testid="kb-answer">
          <InferenceBadge inference={answer.inference} /> <span className="muted">{answer.method}</span>
          {answer.answered ? (
            <ul>
              {answer.answer.map((s, i) => (
                <li key={i}>
                  <blockquote style={{ margin: "0.3rem 0" }}>{s.text}</blockquote>
                  <span className="muted">
                    — {s.citation.document_title} (v{s.citation.version}) › {s.citation.section}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p>{answer.refusal ?? t("kbNotFound")}</p>
          )}
          {answer.note && <p className="muted">{answer.note}</p>}
          {answer.retrieved.length > 0 && (
            <details>
              <summary>{t("kbSources")}</summary>
              <ul>
                {answer.retrieved.map((c) => (
                  <li key={c.chunk_id}>
                    {c.document_title} › {c.section} (BM25 {c.score})
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
      )}
      {manage && (
        <section className="card" style={{ marginTop: "1rem" }}>
          <h2 style={{ marginTop: 0 }}>{t("kbUpload")}</h2>
          <form className="stack" style={{ maxWidth: 640 }} onSubmit={(e) => void upload(e)}>
            <label className="field">
              {t("kbDocTitle")}
              <input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} required />
            </label>
            <label className="field">
              {t("kbDocType")}
              <select value={docType} onChange={(e) => setDocType(e.target.value)}>
                {["sop", "manual", "policy", "training", "other"].map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              {t("kbFile")}
              <input
                type="file"
                accept=".txt,.md,.markdown,text/plain,text/markdown"
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  setFileName(f.name);
                  setText(await f.text());
                  if (!title) setTitle(f.name.replace(/\.(txt|md|markdown)$/i, ""));
                }}
              />
            </label>
            <label className="field">
              {t("kbDocText")}
              <textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} required />
            </label>
            <label className="field">
              {t("kbVisibility")}
              <input value={roles} placeholder="doctor, nurse" onChange={(e) => setRoles(e.target.value)} />
            </label>
            <label>
              <input type="checkbox" checked={noPhi} onChange={(e) => setNoPhi(e.target.checked)} />{" "}
              {t("kbNoPatientData")}
            </label>
            <label>
              <input type="checkbox" checked={hasPhi} onChange={(e) => setHasPhi(e.target.checked)} />{" "}
              {t("kbContainsPatientData")}
            </label>
            <button type="submit" className="primary" disabled={busy || !noPhi || hasPhi}>
              {t("kbSubmit")}
            </button>
          </form>
        </section>
      )}
      <section className="card" style={{ marginTop: "1rem" }}>
        <h2 style={{ marginTop: 0 }}>{t("kbDocuments")}</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t("kbDocTitle")}</th>
                <th>{t("kbVersion")}</th>
                <th>{t("kbStatus")}</th>
                <th>{t("kbInjectionFlags")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id}>
                  <td>
                    {d.title} <span className="muted">({d.doc_type})</span>
                  </td>
                  <td>{d.version}</td>
                  <td>{d.status}</td>
                  <td>{d.injection_flags}</td>
                  <td>
                    {manage && d.status === "draft" && (
                      <button type="button" className="ghost" disabled={busy} onClick={() => void transition(d.id, "approve")}>
                        {t("kbApprove")}
                      </button>
                    )}
                    {manage && d.status !== "archived" && (
                      <button type="button" className="ghost" disabled={busy} onClick={() => void transition(d.id, "archive")}>
                        {t("kbArchive")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

export default function KnowledgePage() {
  const { t } = useLang();
  return (
    <AppShell active="aiKnowledge">
      <main className="page">
        <h1 style={{ marginTop: 0 }}>{t("kbTitle")}</h1>
        <p className="muted">{t("kbIntro")}</p>
        <AiFeatureGate feature="ai_rag">
          <KnowledgeBody />
        </AiFeatureGate>
      </main>
    </AppShell>
  );
}
