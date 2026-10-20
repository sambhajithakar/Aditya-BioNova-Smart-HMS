"use client";

/**
 * Platform console — plan catalogue editor. For one plan at a time:
 *   PATCH /platform/plans/{code}           name, description, prices (₹ → paise),
 *                                          trial days, active / public
 *   PUT   /platform/plans/{code}/features  checklist from /platform/catalog
 *   PUT   /platform/plans/{code}/limits    whole numbers or "unlimited" (null)
 * Prices are typed in rupees and sent as integer paise; an empty price means
 * "not configured" (null, shown to clinics as "Price on request").
 */
import { FormEvent, useCallback, useEffect, useState } from "react";
import { PlatformShell } from "@/components/PlatformShell";
import { Messages, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import {
  Catalog,
  FEATURE_KEYS,
  LIMIT_KEYS,
  PlatformPlanOut,
  formatPaise,
  paiseToRupeesInput,
  parseLimit,
  parseRupeesToPaise,
  serverMessage,
} from "@/lib/saas";

type Draft = {
  name: string;
  description: string;
  monthly: string;
  annual: string;
  trial_days: string;
  is_active: boolean;
  is_public: boolean;
  features: string[];
  limits: Record<string, { unlimited: boolean; value: string }>;
};

function draftFrom(p: PlatformPlanOut, limitKeys: string[]): Draft {
  const limits: Draft["limits"] = {};
  for (const k of limitKeys) {
    const v = p.limits?.[k];
    limits[k] = { unlimited: v === null || v === undefined, value: v == null ? "" : String(v) };
  }
  return {
    name: p.name,
    description: p.description ?? "",
    monthly: paiseToRupeesInput(p.price_monthly_paise),
    annual: paiseToRupeesInput(p.price_annual_paise),
    trial_days: String(p.trial_days ?? 0),
    is_active: p.is_active,
    is_public: p.is_public,
    features: [...p.features],
    limits,
  };
}

function PlansBody() {
  const { t } = useLang();
  const { busy, error, notice, setError, setNotice, act } = useAction();
  const [plans, setPlans] = useState<PlatformPlanOut[]>([]);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [code, setCode] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);

  const featureList = catalog?.features.length
    ? catalog.features
    : FEATURE_KEYS.map((k) => ({ key: k, label: k }));
  const limitList = catalog?.limits.length
    ? catalog.limits
    : LIMIT_KEYS.map((k) => ({ key: k, label: k }));
  const limitKeys = limitList.map((l) => l.key);

  const load = useCallback(async () => {
    try {
      const [p, c] = await Promise.all([
        api.get<PlatformPlanOut[]>("/platform/plans"),
        api.get<Catalog>("/platform/catalog").catch(() => null),
      ]);
      setPlans([...p].sort((a, b) => a.sort_order - b.sort_order || a.tier - b.tier));
      setCatalog(c);
    } catch (err) {
      setError(serverMessage(err, t("loadFailed")));
    }
  }, [setError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const select = (c: string) => {
    setCode(c);
    const p = plans.find((x) => x.code === c);
    setDraft(p ? draftFrom(p, limitKeys) : null);
  };

  const label = (prefix: string, k: string, fallback: string) => {
    const s = t(`${prefix}_${k}`);
    return s === `${prefix}_${k}` ? fallback : s;
  };

  const onSave = (e: FormEvent) => {
    e.preventDefault();
    if (!draft) return;
    const monthly = parseRupeesToPaise(draft.monthly);
    const annual = parseRupeesToPaise(draft.annual);
    if (!monthly.ok || !annual.ok) {
      setError(t("invalidAmount"));
      return;
    }
    const trial = parseLimit(draft.trial_days);
    if (trial === undefined) {
      setError(t("invalidLimit"));
      return;
    }
    const limits: Record<string, number | null> = {};
    for (const [k, l] of Object.entries(draft.limits)) {
      if (l.unlimited) limits[k] = null;
      else {
        const n = parseLimit(l.value);
        if (n === undefined) {
          setError(t("invalidLimit"));
          return;
        }
        limits[k] = n;
      }
    }
    void act(async () => {
      const path = `/platform/plans/${encodeURIComponent(code)}`;
      await api.patch(path, {
        name: draft.name.trim(),
        description: draft.description.trim(),
        price_monthly_paise: monthly.paise,
        price_annual_paise: annual.paise,
        trial_days: trial,
        is_active: draft.is_active,
        is_public: draft.is_public,
      });
      await api.put(`${path}/features`, { features: draft.features });
      await api.put(`${path}/limits`, { limits });
      setNotice(t("saved"));
      const fresh = await api.get<PlatformPlanOut[]>("/platform/plans");
      const sorted = [...fresh].sort((a, b) => a.sort_order - b.sort_order || a.tier - b.tier);
      setPlans(sorted);
      const p = sorted.find((x) => x.code === code);
      if (p) setDraft(draftFrom(p, limitKeys));
    });
  };

  const toggleFeature = (k: string) =>
    draft &&
    setDraft({
      ...draft,
      features: draft.features.includes(k)
        ? draft.features.filter((x) => x !== k)
        : [...draft.features, k],
    });

  const setLimit = (k: string, patch: Partial<{ unlimited: boolean; value: string }>) =>
    draft && setDraft({ ...draft, limits: { ...draft.limits, [k]: { ...draft.limits[k], ...patch } } });

  return (
    <main className="page" style={{ maxWidth: 1280 }}>
      <h1 style={{ marginTop: 0 }}>{t("platformPlans")}</h1>
      <Messages error={error} notice={notice} />

      <section className="card">
        <div className="table-wrap">
          <table data-testid="plans-table">
            <thead>
              <tr>
                <th scope="col">{t("plan")}</th>
                <th scope="col">{t("cycle_monthly")}</th>
                <th scope="col">{t("cycle_annual")}</th>
                <th scope="col">{t("trialDays")}</th>
                <th scope="col">{t("isActive")}</th>
                <th scope="col">{t("isPublic")}</th>
                <th scope="col">{t("actions")}</th>
              </tr>
            </thead>
            <tbody>
              {plans.map((p) => (
                <tr key={p.code} className={p.code === code ? "selected" : undefined}>
                  <td>
                    <strong>{p.name}</strong>
                    <div className="muted" style={{ fontSize: "0.85rem" }}>
                      {p.code}
                    </div>
                  </td>
                  <td>{formatPaise(p.price_monthly_paise) ?? t("priceOnRequest")}</td>
                  <td>{formatPaise(p.price_annual_paise) ?? t("priceOnRequest")}</td>
                  <td>{p.trial_days}</td>
                  <td>{p.is_active ? "✓" : "—"}</td>
                  <td>{p.is_public ? "✓" : "—"}</td>
                  <td>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => select(p.code)}
                      aria-label={`${t("edit")} — ${p.name}`}
                    >
                      {t("edit")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {draft && (
        <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="plan-edit-h">
          <h2 id="plan-edit-h" style={{ marginTop: 0 }}>
            {t("edit")}: {code}
          </h2>
          <form onSubmit={onSave}>
            <div className="grid two">
              <label className="field">
                {t("planName")}
                <input
                  type="text"
                  value={draft.name}
                  maxLength={120}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  required
                />
              </label>
              <label className="field">
                {t("trialDays")}
                <input
                  type="number"
                  min={0}
                  step={1}
                  value={draft.trial_days}
                  onChange={(e) => setDraft({ ...draft, trial_days: e.target.value })}
                  required
                />
              </label>
              <label className="field">
                {t("monthlyPrice")}
                <input
                  type="text"
                  inputMode="decimal"
                  value={draft.monthly}
                  placeholder={t("priceOnRequest")}
                  onChange={(e) => setDraft({ ...draft, monthly: e.target.value })}
                  aria-invalid={!parseRupeesToPaise(draft.monthly).ok || undefined}
                />
              </label>
              <label className="field">
                {t("annualPrice")}
                <input
                  type="text"
                  inputMode="decimal"
                  value={draft.annual}
                  placeholder={t("priceOnRequest")}
                  onChange={(e) => setDraft({ ...draft, annual: e.target.value })}
                  aria-invalid={!parseRupeesToPaise(draft.annual).ok || undefined}
                />
              </label>
            </div>
            <label className="field" style={{ marginTop: "1rem" }}>
              {t("description")}
              <textarea
                className="wide"
                rows={2}
                maxLength={1000}
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              />
            </label>
            <div className="row" style={{ marginTop: "0.75rem" }}>
              <label className="inline">
                <input
                  type="checkbox"
                  checked={draft.is_active}
                  onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })}
                />
                {t("isActive")}
              </label>
              <label className="inline">
                <input
                  type="checkbox"
                  checked={draft.is_public}
                  onChange={(e) => setDraft({ ...draft, is_public: e.target.checked })}
                />
                {t("isPublic")}
              </label>
            </div>

            <h3>{t("features")}</h3>
            <fieldset className="check-grid">
              <legend className="sr-only">{t("features")}</legend>
              {featureList.map((f) => (
                <label key={f.key}>
                  <input
                    type="checkbox"
                    checked={draft.features.includes(f.key)}
                    onChange={() => toggleFeature(f.key)}
                  />
                  {label("feature", f.key, f.label)}
                </label>
              ))}
            </fieldset>

            <h3>{t("limitsTitle")}</h3>
            <div className="grid two">
              {limitList.map((l) => {
                const v = draft.limits[l.key] ?? { unlimited: true, value: "" };
                const name = label("limit", l.key, l.label);
                return (
                  <div className="field" key={l.key}>
                    <span>{name}</span>
                    <div className="row" style={{ alignItems: "center" }}>
                      <input
                        type="number"
                        min={0}
                        step={1}
                        aria-label={name}
                        value={v.unlimited ? "" : v.value}
                        disabled={v.unlimited}
                        onChange={(e) => setLimit(l.key, { value: e.target.value })}
                        style={{ width: 140 }}
                      />
                      <label className="inline" style={{ fontWeight: 500 }}>
                        <input
                          type="checkbox"
                          checked={v.unlimited}
                          aria-label={`${t("unlimited")} — ${name}`}
                          onChange={(e) => setLimit(l.key, { unlimited: e.target.checked })}
                        />
                        {t("unlimited")}
                      </label>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="row" style={{ marginTop: "1rem" }}>
              <button type="submit" className="primary" disabled={busy}>
                {t("savePlan")}
              </button>
              <button type="button" className="secondary" onClick={() => setDraft(null)}>
                {t("cancel")}
              </button>
            </div>
          </form>
        </section>
      )}
    </main>
  );
}

export default function PlatformPlansPage() {
  return (
    <PlatformShell active="plans">
      <PlansBody />
    </PlatformShell>
  );
}
