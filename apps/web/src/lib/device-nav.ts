/**
 * Phone (<768px) bottom navigation: Home + the most-used modules for the
 * member's role, then "More" (a sheet with everything else). Built ONLY from
 * the already-gated nav list (visibleNav: permission + edition feature), so
 * the bottom bar can never show a module the member cannot open.
 */
import type { ShellNavItem } from "./nav";

/** Module slots between Home and More. */
export const BOTTOM_SLOTS = 3;

/** Most-used modules per role, in priority order (keys from lib/nav.ts). */
export const ROLE_PRIORITY: Record<string, string[]> = {
  doctor: ["queue", "consultation", "patients", "lab", "ipd"],
  nurse: ["queue", "ipd", "patients", "consultation"],
  receptionist: ["patients", "appointments", "queue", "billing"],
  pharmacist: ["pharmacy", "inventory", "patients"],
  lab_technician: ["lab", "patients", "queue"],
  billing: ["billing", "patients", "reports"],
  auditor: ["reports", "audit", "patients"],
  support: ["support", "dashboard"],
  owner: ["patients", "queue", "billing", "reports"],
  admin: ["patients", "queue", "billing", "reports"],
};

const FALLBACK = ["patients", "queue", "consultation", "billing", "appointments", "pharmacy", "lab", "ipd", "reports"];

export function pickBottomNav<T extends ShellNavItem>(
  visible: T[],
  role: string | undefined,
  slots = BOTTOM_SLOTS,
): { primary: T[]; rest: T[] } {
  const byKey = new Map(visible.map((i) => [i.key, i]));
  const order = [...(ROLE_PRIORITY[role ?? ""] ?? []), ...FALLBACK];
  const primary: T[] = [];
  for (const k of order) {
    const item = byKey.get(k);
    if (!item || k === "dashboard" || primary.includes(item)) continue;
    primary.push(item);
    if (primary.length >= slots) break;
  }
  const rest = visible.filter((i) => i.key !== "dashboard" && !primary.includes(i));
  return { primary, rest };
}
