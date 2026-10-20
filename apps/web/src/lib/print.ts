import type { Drug, RxItem } from "./api";

/** Display name for an Rx item: Rx detail fields first (M7), catalog fallback. */
export function itemDrugName(it: RxItem, catalog: Record<string, Drug>): {
  name: string;
  detail: string;
} {
  const name = it.drug_name || it.generic_name || catalog[it.drug_id]?.generic_name || "—";
  const parts: string[] = [];
  if (it.generic_name && it.drug_name && it.generic_name !== it.drug_name) parts.push(it.generic_name);
  if (it.strength) parts.push(it.strength);
  if (!it.drug_name && !it.generic_name && catalog[it.drug_id]?.brand_hint) {
    parts.push(catalog[it.drug_id].brand_hint);
  }
  return { name, detail: parts.join(" · ") };
}
