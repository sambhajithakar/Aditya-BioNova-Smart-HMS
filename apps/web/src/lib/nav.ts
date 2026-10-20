/**
 * Module navigation. Each entry is shown only when the member holds `perm`
 * (RBAC, S5) AND the tenant's edition includes `feature` (M7.1 feature
 * gating). `label` is the i18n key (defaults to `key`).
 */
import type { NavItem } from "./saas";

export type ShellNavItem = NavItem & { label?: string };

export const NAV: ShellNavItem[] = [
  { key: "dashboard", href: "/dashboard" },
  { key: "patients", href: "/patients", perm: "patient.read" },
  { key: "appointments", href: "/appointments", perm: "appointment.read", feature: "appointments" },
  { key: "queue", href: "/queue", perm: "queue.read", feature: "opd_queue" },
  { key: "consultation", href: "/consultation", perm: "encounter.read", feature: "consultation" },
  { key: "billing", href: "/billing", perm: "billing.read", feature: "billing" },
  { key: "pharmacy", href: "/pharmacy", perm: "pharmacy.read", feature: "pharmacy" },
  { key: "lab", href: "/lab", perm: "lab.read", feature: "laboratory" },
  { key: "ipd", href: "/ipd", perm: "bed.read", feature: "ipd" },
  { key: "inventory", href: "/inventory", perm: "inventory.read", feature: "inventory" },
  { key: "expenses", href: "/expenses", perm: "expense.read", feature: "expenses" },
  { key: "reports", href: "/reports", perm: "report.read", feature: "reports_basic" },
  { key: "copilot", label: "navCopilot", href: "/copilot", perm: "ai.copilot.use", feature: "ai_copilot" },
  { key: "members", href: "/settings/members", perm: "member.read" },
  { key: "organization", label: "navOrganization", href: "/settings/organization", perm: "org.read" },
  { key: "branches", label: "navBranches", href: "/settings/branches", perm: "branch.read" },
  {
    key: "subscription",
    label: "navSubscription",
    href: "/settings/subscription",
    perm: "subscription.read",
  },
  { key: "support", label: "navSupport", href: "/support", perm: "support.read" },
  { key: "audit", label: "navAudit", href: "/settings/audit", perm: "audit.read" },
  { key: "data", label: "navData", href: "/settings/data", perm: "org.offboard" },
  { key: "security", href: "/settings/security" },
];

export function navLabel(item: ShellNavItem): string {
  return item.label ?? item.key;
}
