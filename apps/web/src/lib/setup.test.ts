import { describe, expect, it } from "vitest";
import { baseDictionaries, dictionaries } from "./i18n";
import { aiDictionaries } from "./i18n-ai";
import { saasDictionaries } from "./i18n-saas";
import { setupDictionaries } from "./i18n-setup";
import {
  PAYMENT_METHODS,
  PRINT_DOCUMENTS,
  PRINTER_KINDS,
  PrinterProfile,
  WIZARD_STEPS,
  WizardState,
  cleanSessions,
  defaultWeek,
  feeInput,
  formatCheckinCode,
  neighbourStep,
  normalizeCheckinCode,
  pageCss,
  pageGeometry,
  parseFee,
  resumeStep,
  workingHoursErrors,
} from "./setup";

const TOKEN = "K7Q2MZJX4WNB5TRC3HPLYD6VAE";

describe("working hours", () => {
  it("accepts the default week and split sessions", () => {
    expect(workingHoursErrors(defaultWeek())).toEqual([]);
    expect(
      workingHoursErrors([
        { weekday: 6, opens_at: "09:00", closes_at: "12:00", break_starts_at: null, break_ends_at: null },
        { weekday: 6, opens_at: "17:00", closes_at: "20:00", break_starts_at: null, break_ends_at: null },
      ]),
    ).toEqual([]);
  });

  it("flags inverted ranges, bad breaks and overlaps like the API", () => {
    const s = (o: string, c: string, bs: string | null = null, be: string | null = null, d = 0) => ({
      weekday: d,
      opens_at: o,
      closes_at: c,
      break_starts_at: bs,
      break_ends_at: be,
    });
    expect(workingHoursErrors([s("18:00", "09:00")])[0].code).toBe("range");
    expect(workingHoursErrors([s("09:00", "12:00", "11:00", "12:30")])[0].code).toBe("break");
    expect(workingHoursErrors([s("09:00", "12:00", "11:00")])[0].code).toBe("breakHalf");
    expect(workingHoursErrors([s("9am", "12:00")])[0].code).toBe("time");
    expect(workingHoursErrors([s("09:00", "13:00"), s("12:30", "15:00")])).toEqual([
      { weekday: 0, code: "overlap" },
    ]);
    // the same times on different days never overlap
    expect(workingHoursErrors([s("09:00", "13:00"), s("09:00", "13:00", null, null, 1)])).toEqual([]);
  });

  it("normalises server times before sending", () => {
    expect(
      cleanSessions([
        { weekday: 1, opens_at: "09:00:00", closes_at: "18:00:00", break_starts_at: "", break_ends_at: "" },
      ]),
    ).toEqual([{ weekday: 1, opens_at: "09:00", closes_at: "18:00", break_starts_at: null, break_ends_at: null }]);
  });
});

describe("check-in codes", () => {
  it("normalises spacing, case and look-alike digits", () => {
    expect(normalizeCheckinCode(formatCheckinCode(TOKEN).toLowerCase())).toBe(TOKEN);
    expect(normalizeCheckinCode("K7Q2-MZJX-4WNB-5TRC-3HPL-YD6V-AE")).toBe(TOKEN);
    expect(normalizeCheckinCode(TOKEN.replace(/O/g, "0"))).toBe(TOKEN);
    expect(normalizeCheckinCode("hello")).toBeNull();
    expect(normalizeCheckinCode(TOKEN + "A")).toBeNull();
    expect(normalizeCheckinCode("")).toBeNull();
  });

  it("formats in groups of four", () => {
    expect(formatCheckinCode(TOKEN)).toBe("K7Q2 MZJX 4WNB 5TRC 3HPL YD6V AE");
  });
});

describe("fees", () => {
  it("parses rupee inputs strictly", () => {
    expect(parseFee("350")).toBe("350.00");
    expect(parseFee(" 99.5 ")).toBe("99.50");
    expect(parseFee("")).toBeNull();
    expect(parseFee("-1")).toBeUndefined();
    expect(parseFee("1.234")).toBeUndefined();
    expect(parseFee("2000000")).toBeUndefined();
    expect(parseFee("abc")).toBeUndefined();
    expect(feeInput("350.00")).toBe("350");
    expect(feeInput("99.50")).toBe("99.50");
    expect(feeInput(null)).toBe("");
  });
});

describe("printer page geometry", () => {
  const profile = (over: Partial<PrinterProfile>): PrinterProfile => ({
    id: "p",
    name: "x",
    kind: "a5",
    default_for: [],
    margin_top_mm: "8.0",
    margin_right_mm: "10.0",
    margin_bottom_mm: "8.0",
    margin_left_mm: "12.0",
    font_scale: "1.10",
    notes: "",
    created_at: "",
    updated_at: "",
    ...over,
  });

  it("maps profiles to @page size and margins", () => {
    const g = pageGeometry(profile({}));
    expect(g.size).toBe("A5");
    expect(g.margins).toEqual([8, 10, 8, 12]);
    expect(g.contentWidthMm).toBe(126);
    const css = pageCss(g);
    expect(css).toContain("@page { size: A5; margin: 8mm 10mm 8mm 12mm; }");
    expect(css).toContain("font-size: 110%");
  });

  it("uses roll paper for thermal printers and safe fallbacks", () => {
    expect(pageGeometry(profile({ kind: "thermal_58mm" })).size).toBe("58mm auto");
    const none = pageGeometry(null);
    expect(none.size).toBe("A4");
    expect(none.margins).toEqual([12, 12, 12, 12]);
    const hostile = pageGeometry(profile({ margin_top_mm: "999", font_scale: "9" }));
    expect(hostile.margins[0]).toBe(12);
    expect(hostile.fontScale).toBe(1);
    expect(pageCss(hostile)).not.toMatch(/[<>{]\s*script/i);
  });
});

describe("wizard helpers", () => {
  const state = (current: string): WizardState => ({
    steps: WIZARD_STEPS.map((key, i) => ({ key, status: i < 2 ? "done" : "todo", data_ready: false })),
    current_step: current as WizardState["current_step"],
    finished: false,
    finished_at: null,
    should_show: true,
    progress_percent: 18,
  });
  it("resumes where the server says", () => {
    expect(resumeStep(state("fees"))).toBe("fees");
    expect(resumeStep(state("bogus"))).toBe("staff");
    expect(resumeStep(null)).toBe("identity");
    expect(neighbourStep("identity", -1)).toBeNull();
    expect(neighbourStep("identity", 1)).toBe("branch");
    expect(neighbourStep("edition", 1)).toBeNull();
  });
});

describe("setup i18n", () => {
  it("EN / मराठी / हिंदी key sets match and are merged", () => {
    const en = Object.keys(setupDictionaries.en).sort();
    expect(Object.keys(setupDictionaries.mr).sort()).toEqual(en);
    expect(Object.keys(setupDictionaries.hi).sort()).toEqual(en);
    for (const k of en) expect(dictionaries.hi[k]).toBe(setupDictionaries.hi[k]);
  });
  it("never silently overrides an existing key", () => {
    const others = { ...baseDictionaries.en, ...saasDictionaries.en, ...aiDictionaries.en };
    expect(Object.keys(setupDictionaries.en).filter((k) => k in others)).toEqual([]);
  });
  it("dynamic key families exist", () => {
    const d = dictionaries.en;
    for (const k of WIZARD_STEPS) expect(d).toHaveProperty(`wizStep_${k}`);
    for (const k of PRINTER_KINDS) expect(d).toHaveProperty(`printerKind_${k}`);
    for (const k of PRINT_DOCUMENTS) expect(d).toHaveProperty(`printDoc_${k}`);
    for (const k of PAYMENT_METHODS) expect(d).toHaveProperty(`payMethod_${k}`);
    for (let i = 0; i < 7; i++) expect(d).toHaveProperty(`weekday_${i}`);
  });
});
