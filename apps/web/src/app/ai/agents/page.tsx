"use client";

/**
 * AI-1 proposal inbox: run a deterministic agent, review the exact proposal
 * with its rationale and evidence, approve or reject. Approval executes only
 * the safe action of that kind, as the approving user, after re-validation.
 */
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { AiFeatureGate, InferenceBadge } from "@/components/AiCommon";
import { Messages, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { useCan } from "@/lib/me";

const AGENTS = ["appointment_followups", "inventory_monitor", "billing_reconciliation", "ops_daily_report"];

type Proposal = {
  id: string;
  agent: string;
  kind: string;
  status: string;
  title: string;
  payload: Record<string, unknown>;
  rationale: string;
  evidence: { type: string; id: string }[];
  expires_at: string;
  result: Record<string, unknown> | null;
  approve_requires: string[];
};
type Task = { id: string; title: string; priority: string; status: string; due_date: string | null };

function AgentsBody() {
  const { t } = useLang();
  const can = useCan();
  const approver = can("ai.agents.approve");
  const { busy, error, notice, act } = useAction();
  const [agent, setAgent] = useState(AGENTS[0]);
  const [items, setItems] = useState<Proposal[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);

  const load = useCallback(async () => {
    setItems(await api.get<Proposal[]>("/ai/agents/proposals"));
    if (can("appointment.read")) setTasks(await api.get<Task[]>("/ai/agents/tasks"));
  }, [can]);

  useEffect(() => {
    void act(load);
  }, [act, load]);

  const run = () =>
    act(async () => {
      await api.post("/ai/agents/run", { agent, older_than_days: 7 });
      await load();
    });
  const decide = (id: string, d: "approve" | "reject") =>
    act(async () => {
      await api.post(`/ai/agents/proposals/${id}/${d}`, { note: "" });
      await load();
    });
  const done = (id: string) =>
    act(async () => {
      await api.post(`/ai/agents/tasks/${id}/done`, {});
      await load();
    });

  return (
    <>
      <Messages error={error} notice={notice} />
      <section className="card row">
        <label className="field grow">
          {t("agAgent")}
          <select value={agent} onChange={(e) => setAgent(e.target.value)}>
            {AGENTS.map((a) => (
              <option key={a} value={a}>
                {t(`ag_${a}`)}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="primary" disabled={busy} onClick={() => void run()}>
          {t("agRun")}
        </button>
        <InferenceBadge inference="deterministic" />
      </section>
      {items.length === 0 && <p className="muted">{t("agNone")}</p>}
      {items.map((p) => (
        <article key={p.id} className="card" style={{ marginTop: "1rem" }} data-testid="proposal">
          <h3 style={{ marginTop: 0 }}>
            {p.title} <span className="badge">{p.status}</span>
          </h3>
          <p>
            <strong>{t("agRationale")}:</strong> {p.rationale}
          </p>
          <p className="muted">
            {t("agRequires")}: {p.approve_requires.join(", ")} · {t("agExpires")}:{" "}
            {new Date(p.expires_at).toLocaleString()}
          </p>
          <details>
            <summary>{t("agPayload")}</summary>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.8rem" }}>{JSON.stringify(p.payload, null, 2)}</pre>
          </details>
          <details>
            <summary>
              {t("agEvidence")} ({p.evidence.length})
            </summary>
            <ul>
              {p.evidence.slice(0, 50).map((e, i) => (
                <li key={i}>
                  {e.type}: <code>{e.id}</code>
                </li>
              ))}
            </ul>
          </details>
          {p.result && (
            <p>
              <strong>{t("agResult")}:</strong> <code>{JSON.stringify(p.result)}</code>
            </p>
          )}
          {approver && p.status === "proposed" && (
            <div className="row">
              <button type="button" className="primary" disabled={busy} onClick={() => void decide(p.id, "approve")}>
                {t("agApprove")}
              </button>
              <button type="button" className="ghost" disabled={busy} onClick={() => void decide(p.id, "reject")}>
                {t("agReject")}
              </button>
            </div>
          )}
        </article>
      ))}
      {tasks.length > 0 && (
        <section className="card" style={{ marginTop: "1rem" }}>
          <h2 style={{ marginTop: 0 }}>{t("agTasks")}</h2>
          <ul>
            {tasks.map((x) => (
              <li key={x.id}>
                {x.priority === "high" ? "⚑ " : ""}
                {x.title}{" "}
                {can("appointment.write") && (
                  <button type="button" className="ghost" disabled={busy} onClick={() => void done(x.id)}>
                    {t("agDone")}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

export default function AgentsPage() {
  const { t } = useLang();
  return (
    <AppShell active="aiAgents">
      <main className="page">
        <h1 style={{ marginTop: 0 }}>{t("agTitle")}</h1>
        <p className="muted">{t("agIntro")}</p>
        <AiFeatureGate feature="ai_agents">
          <AgentsBody />
        </AiFeatureGate>
      </main>
    </AppShell>
  );
}
