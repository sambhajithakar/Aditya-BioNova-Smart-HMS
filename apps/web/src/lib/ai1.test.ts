import { describe, expect, it } from "vitest";
import { chartGeometry } from "./ai1";
import { dictionaries } from "./i18n";
import { NAV } from "./nav";

describe("AI-1 web", () => {
  it("agent label family is complete in every language", () => {
    for (const lang of ["en", "mr", "hi"] as const)
      for (const a of ["appointment_followups", "inventory_monitor", "billing_reconciliation", "ops_daily_report"])
        expect(dictionaries[lang]).toHaveProperty(`ag_${a}`);
  });

  it("AI-1 nav entries are permission- and edition-gated", () => {
    const ai = NAV.filter((n) => n.href.startsWith("/ai/"));
    expect(ai.map((n) => n.feature)).toEqual(["ai_forecast", "ai_rag", "ai_agents", "ai_scribe"]);
    for (const n of ai) expect(n.perm).toMatch(/^ai\./);
  });

  it("chart geometry maps history + forecast with an 80% band", () => {
    const g = chartGeometry(
      [
        { date: "d1", value: 2 },
        { date: "d2", value: 4 },
      ],
      [{ date: "d3", point: 5, lo80: 4, hi80: 6, lo95: 3, hi95: 8 }],
    );
    expect(g.max).toBe(8);
    expect(g.history.startsWith("M")).toBe(true);
    expect(g.band80.endsWith("Z")).toBe(true);
    expect(chartGeometry([], []).band80).toBe("");
  });
});
