"use client";

/**
 * AI-1 forecasts: statistical models (not an AI service). Every card shows the
 * method, training window, backtest error next to the naive baseline and,
 * when history is too short, what is needed instead of a chart.
 */
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import {
  AiFeatureGate,
  ForecastChart,
  ForecastPoint,
  InferenceBadge,
  Insufficient,
  InsufficientNotice,
} from "@/components/AiCommon";
import { Messages, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { useCan } from "@/lib/me";

type Metrics = { method: string; mae: number; mape_percent: number | null; folds: number };
type SeriesOk = {
  status: "ok";
  inference: string;
  method: string;
  method_label: string;
  training_window: { start: string; end: string; days: number };
  backtest: { selected: Metrics; baseline: Metrics; beats_baseline: boolean };
  history: { date: string; value: number }[];
  forecast: ForecastPoint[];
  branch_name?: string;
  unit?: string;
  beds_total?: number;
};
type Series = SeriesOk | (Insufficient & { branch_name?: string });
type DemandRow = {
  status: string;
  name: string;
  on_hand: number;
  avg_daily_use?: number;
  days_of_cover?: number | null;
  suggested_order_qty?: number;
  projected_expiring_unused?: number;
  method?: string;
  backtest?: { selected: Metrics; baseline: Metrics };
  required?: string;
};
type Factor = { description: string; effect: string };
type NoShow =
  | (Insufficient & { intended_use: string })
  | {
      status: "ok";
      inference: string;
      intended_use: string;
      method_label: string;
      backtest: { selected: { brier: number; auc: number | null }; baseline: { brier: number } };
      predictions: { appointment_id: string; starts_at: string; risk: number; band: string; factors: Factor[] }[];
    };

function SeriesCard({ title, s }: { title: string; s: Series }) {
  const { t } = useLang();
  return (
    <section className="card" style={{ marginTop: "1rem" }} data-testid="forecast-card">
      <h2 style={{ marginTop: 0 }}>
        {title}
        {s.branch_name ? ` — ${s.branch_name}` : ""}
      </h2>
      <InferenceBadge inference="statistical" />
      {s.status !== "ok" ? (
        <InsufficientNotice r={s} />
      ) : (
        <>
          <ForecastChart history={s.history} forecast={s.forecast} label={title} />
          <dl>
            <dt>{t("fcMethod")}</dt>
            <dd>{s.method_label}</dd>
            <dt>{t("fcWindow")}</dt>
            <dd>
              {s.training_window.start} → {s.training_window.end} ({s.training_window.days})
            </dd>
            <dt>{t("fcBacktest")}</dt>
            <dd>
              {s.backtest.selected.mae} ({s.backtest.selected.folds} folds) · {t("fcBaseline")}:{" "}
              {s.backtest.baseline.mae} ·{" "}
              {s.backtest.beats_baseline ? t("fcBeatsBaseline") : t("fcNotBetter")}
            </dd>
          </dl>
        </>
      )}
    </section>
  );
}

function ForecastsBody() {
  const { t } = useLang();
  const can = useCan();
  const { busy, error, notice, act } = useAction();
  const [opd, setOpd] = useState<Series[]>([]);
  const [beds, setBeds] = useState<Series | null>(null);
  const [drugs, setDrugs] = useState<DemandRow[]>([]);
  const [noShow, setNoShow] = useState<NoShow | null>(null);

  const load = useCallback(async () => {
    await act(async () => {
      setOpd(await api.get<Series[]>("/ai/forecast/opd"));
      if (can("bed.read")) setBeds(await api.get<Series>("/ai/forecast/beds").catch(() => null));
      if (can("pharmacy.read")) setDrugs(await api.get<DemandRow[]>("/ai/forecast/pharmacy"));
      if (can("appointment.read")) setNoShow(await api.get<NoShow>("/ai/forecast/no-show"));
    });
  }, [act, can]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <Messages error={error} notice={notice} />
      <button type="button" className="ghost" disabled={busy} onClick={() => void load()}>
        {t("fcLoad")}
      </button>
      {opd.map((s, i) => (
        <SeriesCard key={i} title={t("fcOpd")} s={s} />
      ))}
      {beds && <SeriesCard title={t("fcBeds")} s={beds} />}
      {drugs.length > 0 && (
        <section className="card" style={{ marginTop: "1rem" }}>
          <h2 style={{ marginTop: 0 }}>{t("fcPharmacy")}</h2>
          <InferenceBadge inference="statistical" />
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("fcDrug")}</th>
                  <th>{t("fcOnHand")}</th>
                  <th>{t("fcDailyUse")}</th>
                  <th>{t("fcCover")}</th>
                  <th>{t("fcSuggest")}</th>
                  <th>{t("fcExpiring")}</th>
                  <th>{t("fcMethod")}</th>
                </tr>
              </thead>
              <tbody>
                {drugs.map((d, i) => (
                  <tr key={i}>
                    <td>{d.name}</td>
                    <td>{d.on_hand}</td>
                    {d.status === "ok" ? (
                      <>
                        <td>{d.avg_daily_use}</td>
                        <td>{d.days_of_cover ?? "—"}</td>
                        <td>{d.suggested_order_qty}</td>
                        <td>{d.projected_expiring_unused}</td>
                        <td>
                          {d.method} (MAE {d.backtest?.selected.mae} vs {d.backtest?.baseline.mae})
                        </td>
                      </>
                    ) : (
                      <td colSpan={5} className="muted">
                        {t("aiInsufficient")}: {d.required}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {noShow && (
        <section className="card" style={{ marginTop: "1rem" }}>
          <h2 style={{ marginTop: 0 }}>{t("fcNoShow")}</h2>
          <InferenceBadge inference="statistical" />
          <p className="notice">{t("fcNoShowUse")}</p>
          {noShow.status !== "ok" ? (
            <InsufficientNotice r={noShow} />
          ) : (
            <>
              <p className="muted">
                {noShow.method_label} · Brier {noShow.backtest.selected.brier} ({t("fcBaseline")}{" "}
                {noShow.backtest.baseline.brier})
              </p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>{t("fcAppointment")}</th>
                      <th>{t("fcRisk")}</th>
                      <th>{t("fcFactors")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {noShow.predictions.map((p) => (
                      <tr key={p.appointment_id}>
                        <td>{new Date(p.starts_at).toLocaleString()}</td>
                        <td>
                          {Math.round(p.risk * 100)}% ({p.band})
                        </td>
                        <td>{p.factors.map((f) => `${f.description} (${f.effect})`).join("; ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      )}
    </>
  );
}

export default function ForecastsPage() {
  const { t } = useLang();
  return (
    <AppShell active="aiForecasts">
      <main className="page">
        <h1 style={{ marginTop: 0 }}>{t("fcTitle")}</h1>
        <p className="muted">{t("fcIntro")}</p>
        <AiFeatureGate feature="ai_forecast">
          <ForecastsBody />
        </AiFeatureGate>
      </main>
    </AppShell>
  );
}
