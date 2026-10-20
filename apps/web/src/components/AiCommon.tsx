"use client";

/**
 * AI-1 shared UI: tenant opt-in gate, honest inference labels, the
 * "insufficient data" notice and a dependency-free inline-SVG forecast chart
 * (history line + forecast line + 80 % band + 95 % lines).
 */
import { ReactNode, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ForecastPoint, chartGeometry } from "@/lib/ai1";
import { useLang } from "@/lib/lang";
import { useCan } from "@/lib/me";

type AiSettings = { enabled_features: string[]; entitled_features: string[] };

/** Renders children once the feature is on; admins can switch it on here. */
export function AiFeatureGate({ feature, children }: { feature: string; children: ReactNode }) {
  const { t } = useLang();
  const can = useCan();
  const manage = can("ai.settings.manage");
  const [enabled, setEnabled] = useState<boolean | null>(manage ? null : true);
  const [settings, setSettings] = useState<AiSettings | null>(null);

  const load = useCallback(async () => {
    if (!manage) return;
    try {
      const s = await api.get<AiSettings>("/ai/settings");
      setSettings(s);
      setEnabled(s.enabled_features.includes(feature));
    } catch {
      setEnabled(true); // fall back to the API's own 403 messages
    }
  }, [manage, feature]);

  useEffect(() => {
    void load();
  }, [load]);

  async function enable() {
    const wanted = Array.from(new Set([...(settings?.enabled_features ?? []), feature]));
    await api.patch<AiSettings>("/ai/settings", { enabled_features: wanted });
    setEnabled(true);
  }

  if (enabled === null) return null;
  if (!enabled)
    return (
      <section className="card" data-testid="ai-disabled">
        <p>{t("aiNotEnabled")}</p>
        {manage ? (
          <button type="button" className="primary" onClick={() => void enable()}>
            {t("aiEnableFeature")}
          </button>
        ) : (
          <p className="muted">{t("aiAskAdmin")}</p>
        )}
      </section>
    );
  return <>{children}</>;
}

export function InferenceBadge({ inference }: { inference: string }) {
  const { t } = useLang();
  const label =
    inference === "statistical"
      ? t("aiStatLabel")
      : inference === "live"
        ? t("aiLiveLabel")
        : inference === "deterministic"
          ? t("agDeterministic")
          : t("aiMockLabel");
  return (
    <span className="badge" data-testid="inference-label">
      {label}
    </span>
  );
}

export type Insufficient = {
  status: "insufficient_data";
  required: string;
  available: string;
  earliest_available_on: string | null;
};

export function InsufficientNotice({ r }: { r: Insufficient }) {
  const { t } = useLang();
  return (
    <div className="notice" role="status" data-testid="insufficient">
      <strong>{t("aiInsufficient")}</strong> — {t("aiRequired")}: {r.required}; {t("aiAvailable")}:{" "}
      {r.available}
      {r.earliest_available_on ? ` · ${t("aiEarliest")} ${r.earliest_available_on}` : ""}
    </div>
  );
}

export type { ForecastPoint } from "@/lib/ai1";

export function ForecastChart({
  history,
  forecast,
  label,
}: {
  history: { date: string; value: number }[];
  forecast: ForecastPoint[];
  label: string;
}) {
  const { t } = useLang();
  const g = chartGeometry(history, forecast);
  return (
    <figure style={{ margin: 0 }}>
      <svg
        viewBox={`0 0 ${g.width} ${g.height}`}
        role="img"
        aria-label={label}
        style={{ width: "100%", height: "auto", maxWidth: g.width }}
      >
        <line x1={g.pad} x2={g.width - g.pad} y1={g.height - g.pad} y2={g.height - g.pad} stroke="#94a3b8" />
        <text x={2} y={g.pad} fontSize="11" fill="#475569">
          {Math.round(g.max)}
        </text>
        <line x1={g.splitX} x2={g.splitX} y1={g.pad / 2} y2={g.height - g.pad} stroke="#cbd5e1" strokeDasharray="4 3" />
        <path d={g.band80} fill="#0d9488" fillOpacity={0.18} stroke="none" />
        <path d={g.hi95} fill="none" stroke="#0d9488" strokeOpacity={0.5} strokeDasharray="3 3" />
        <path d={g.lo95} fill="none" stroke="#0d9488" strokeOpacity={0.5} strokeDasharray="3 3" />
        <path d={g.history} fill="none" stroke="#334155" strokeWidth={1.5} />
        <path d={g.forecast} fill="none" stroke="#0d9488" strokeWidth={2} />
      </svg>
      <figcaption className="muted" style={{ fontSize: "0.85rem" }}>
        {t("fcHistory")} — {t("fcForecast")} · {t("fcInterval")}
      </figcaption>
    </figure>
  );
}
