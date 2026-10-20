"use client";

/**
 * BioNova Business Copilot (AI-0). Questions in English / मराठी / हिंदी are
 * mapped to ONE whitelisted report; the figures are computed by the API from
 * the clinic's own records. Every answer shows whether a model or the
 * rule-based parser chose the report ("mock" vs "live" inference) and exactly
 * what was computed. Needs ai.copilot.use + the ai_copilot edition feature;
 * switching the feature on needs ai.settings.manage.
 */
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Messages, useAction } from "@/components/Saas";
import { ApiError, api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { useCan } from "@/lib/me";
import { serverMessage } from "@/lib/saas";

type CopilotAnswer = {
  request_id: string;
  answered: boolean;
  language: string;
  answer: string;
  figures: Record<string, unknown>;
  rows: Record<string, unknown>[];
  computed_with: { function: string; args: Record<string, unknown>; method: string } | null;
  inference: "mock" | "live";
  provider: string;
  model: string;
  credits_charged: number;
  note: string | null;
};

type AiSettings = { enabled_features: string[]; entitled_features: string[] };

const EXAMPLES: Record<string, string[]> = {
  en: ["What were our collections this month?", "Expenses last week", "How many appointments today?",
       "Bed occupancy", "Medicines expiring in 60 days"],
  mr: ["या महिन्यात किती वसुली झाली?", "मागील आठवड्याचा खर्च किती?", "आज किती अपॉइंटमेंट आहेत?"],
  hi: ["इस महीने का कलेक्शन कितना है?", "पिछले हफ्ते का खर्च बताओ", "कितने बेड भर्ती हैं?"],
};

function CopilotBody() {
  const { lang, t } = useLang();
  const can = useCan();
  const manage = can("ai.settings.manage");
  const { busy, error, notice, setError, act } = useAction();
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<(CopilotAnswer & { question: string })[]>([]);
  const [enabled, setEnabled] = useState<boolean | null>(null);

  const loadSettings = useCallback(async () => {
    if (!manage) {
      setEnabled(true); // non-admins find out on their first question
      return;
    }
    try {
      const s = await api.get<AiSettings>("/ai/settings");
      setEnabled(s.enabled_features.includes("ai_copilot"));
    } catch (err) {
      setError(serverMessage(err, t("loadFailed")));
    }
  }, [manage, setError, t]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  async function enable() {
    await act(async () => {
      await api.patch<AiSettings>("/ai/settings", { enabled_features: ["ai_copilot"] });
      setEnabled(true);
    });
  }

  async function ask(e: FormEvent, q = question) {
    e.preventDefault();
    if (!q.trim()) return;
    await act(async () => {
      try {
        // the API answers in the language the question is written in
        const a = await api.post<CopilotAnswer>("/ai/copilot/ask", { question: q });
        setAnswers((prev) => [{ ...a, question: q }, ...prev].slice(0, 20));
        setQuestion("");
      } catch (err) {
        if (err instanceof ApiError && err.detail === "ai_not_enabled") {
          setEnabled(false);
          return;
        }
        throw err;
      }
    });
  }

  return (
    <main className="page">
      <h1 style={{ marginTop: 0 }}>{t("copilotTitle")}</h1>
      <p className="muted">{t("copilotIntro")}</p>
      <Messages error={error} notice={notice} />

      {enabled === false && (
        <section className="card" data-testid="copilot-disabled">
          <p>{t("copilotEnablePrompt")}</p>
          {manage ? (
            <>
              <p className="muted">{t("copilotEnableNotice")}</p>
              <button type="button" className="primary" disabled={busy} onClick={() => void enable()}>
                {t("copilotEnable")}
              </button>
            </>
          ) : (
            <p className="muted">{t("copilotNotEnabledAskAdmin")}</p>
          )}
        </section>
      )}

      {enabled && (
        <section className="card">
          <form className="stack" onSubmit={(e) => void ask(e)}>
            <label className="field">
              {t("copilotAskLabel")}
              <input
                type="text"
                maxLength={500}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                required
              />
            </label>
            <button type="submit" className="primary" disabled={busy}>
              {t("copilotAsk")}
            </button>
          </form>
          <p className="muted" style={{ marginBottom: 0 }}>
            {t("copilotExamples")}{" "}
            {(EXAMPLES[lang] ?? EXAMPLES.en).map((ex) => (
              <button
                key={ex}
                type="button"
                className="ghost chip"
                disabled={busy}
                onClick={(e) => void ask(e as unknown as FormEvent, ex)}
                style={{ margin: "0.2rem" }}
              >
                {ex}
              </button>
            ))}
          </p>
        </section>
      )}

      {answers.length > 0 && <h2>{t("copilotHistory")}</h2>}
      {answers.map((a) => (
        <article key={a.request_id} className="card" data-testid="copilot-answer" style={{ marginTop: "1rem" }}>
          <p className="muted" style={{ marginTop: 0 }}>
            “{a.question}”
          </p>
          <p style={{ fontSize: "1.15rem", fontWeight: 600 }}>
            {a.answered ? a.answer : `${t("copilotNotAnswered")}: ${a.answer}`}
          </p>
          <p>
            <span className="badge" data-testid="inference-label">
              {a.inference === "mock" ? t("copilotInferenceMock") : t("copilotInferenceLive")}
            </span>{" "}
            <span className="muted">
              {a.provider} · {a.model} · {t("copilotCredits")}: {a.credits_charged}
            </span>
          </p>
          {a.note && <p className="muted">{a.note}</p>}
          {a.rows.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    {Object.keys(a.rows[0]).map((k) => (
                      <th key={k}>{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {a.rows.slice(0, 20).map((r, i) => (
                    <tr key={i}>
                      {Object.values(r).map((v, j) => (
                        <td key={j}>{String(v)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {a.computed_with && (
            <details data-testid="how-computed">
              <summary>{t("copilotHowComputed")}</summary>
              <dl>
                <dt>{t("copilotFunction")}</dt>
                <dd>
                  <code>{a.computed_with.function}</code>
                </dd>
                <dt>{t("copilotArgs")}</dt>
                <dd>
                  <code>{JSON.stringify(a.computed_with.args)}</code>
                </dd>
                <dt>{t("copilotMethod")}</dt>
                <dd>{a.computed_with.method}</dd>
              </dl>
            </details>
          )}
        </article>
      ))}
      <p className="muted" style={{ marginTop: "1.5rem" }}>
        {t("copilotDisclaimer")}
      </p>
    </main>
  );
}

export default function CopilotPage() {
  return (
    <AppShell active="copilot">
      <CopilotBody />
    </AppShell>
  );
}
