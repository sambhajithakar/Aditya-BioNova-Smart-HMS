import { describe, expect, it } from "vitest";
import { emptyRxItem, isRxItemValid, toRxItemIn, validateRxItem } from "./rx";

const drug = { id: "11111111-1111-4111-8111-111111111111", generic_name: "Paracetamol" };

function filled(over: Partial<ReturnType<typeof emptyRxItem>> = {}) {
  return {
    ...emptyRxItem(drug),
    dose: "500 mg",
    route: "oral",
    frequency: "TDS",
    duration_days: "5",
    ...over,
  };
}

describe("Rx item builder", () => {
  it("starts with NO silent clinical defaults", () => {
    const it0 = emptyRxItem(drug);
    expect(it0.dose).toBe("");
    expect(it0.route).toBe("");
    expect(it0.frequency).toBe("");
    expect(it0.duration_days).toBe("");
    expect(it0.dispense_quantity).toBe("");
    expect(isRxItemValid(it0)).toBe(false);
    expect(validateRxItem(it0)).toEqual({
      dose: "rxErrRequired",
      route: "rxErrRequired",
      frequency: "rxErrRequired",
      duration_days: "rxErrRequired",
    });
  });

  it("accepts a fully specified item", () => {
    expect(validateRxItem(filled())).toEqual({});
  });

  it.each([
    ["0", "rxErrDuration"],
    ["366", "rxErrDuration"],
    ["2.5", "rxErrDuration"],
    ["abc", "rxErrDuration"],
  ])("rejects duration %s", (d, err) => {
    expect(validateRxItem(filled({ duration_days: d })).duration_days).toBe(err);
  });

  it("validates dispense_quantity as optional int 1..10000", () => {
    expect(validateRxItem(filled({ dispense_quantity: "" })).dispense_quantity).toBeUndefined();
    expect(validateRxItem(filled({ dispense_quantity: "15" })).dispense_quantity).toBeUndefined();
    expect(validateRxItem(filled({ dispense_quantity: "0" })).dispense_quantity).toBe("rxErrDispenseQty");
    expect(validateRxItem(filled({ dispense_quantity: "10001" })).dispense_quantity).toBe("rxErrDispenseQty");
    expect(validateRxItem(filled({ dispense_quantity: "1.5" })).dispense_quantity).toBe("rxErrDispenseQty");
  });

  it("enforces backend length limits and allowed routes", () => {
    expect(validateRxItem(filled({ dose: "x".repeat(101) })).dose).toBe("rxErrTooLong");
    expect(validateRxItem(filled({ instructions: "x".repeat(501) })).instructions).toBe("rxErrTooLong");
    expect(validateRxItem(filled({ quantity: "x".repeat(101) })).quantity).toBe("rxErrTooLong");
    expect(validateRxItem(filled({ route: "IV" })).route).toBe("rxErrRequired");
    expect(validateRxItem(filled({ dose: "   " })).dose).toBe("rxErrRequired");
  });

  it("serialises to RxItemIn, omitting a blank dispense_quantity", () => {
    const out = toRxItemIn(filled({ quantity: " 15 tablets ", instructions: "after food" }));
    expect(out).toEqual({
      drug_id: drug.id,
      dose: "500 mg",
      route: "oral",
      frequency: "TDS",
      duration_days: 5,
      quantity: "15 tablets",
      instructions: "after food",
    });
    expect("dispense_quantity" in out).toBe(false);
    expect(toRxItemIn(filled({ dispense_quantity: "15" })).dispense_quantity).toBe(15);
  });
});
