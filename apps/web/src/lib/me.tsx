"use client";

/**
 * The signed-in member (from GET /auth/me), provided by <AppShell> once the
 * session is established. Pages use it for RBAC-aware rendering and the
 * user's own branch as the default branch (D15).
 */
import { createContext, useContext } from "react";
import type { Branch, Me } from "./api";

export const MeContext = createContext<Me | null>(null);

export function useMe(): Me | null {
  return useContext(MeContext);
}

export function hasPermission(me: Me | null, perm: string | undefined): boolean {
  if (!perm) return true;
  return !!me && me.permissions.includes(perm);
}

/** `can("billing.refund")` for the current member. */
export function useCan(): (perm: string) => boolean {
  const me = useMe();
  return (perm: string) => hasPermission(me, perm);
}

/**
 * Default branch for new records: the member's own branch when it is still
 * active, else the first active branch.
 */
export function defaultBranchId(me: Me | null, branches: Branch[]): string {
  const active = branches.filter((b) => b.status === "active");
  if (me?.branch_id && active.some((b) => b.id === me.branch_id)) return me.branch_id;
  return active[0]?.id ?? "";
}
