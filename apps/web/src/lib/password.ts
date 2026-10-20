/** Backend password policy (M7 contract): 10..200 characters. */
export const PASSWORD_MIN = 10;
export const PASSWORD_MAX = 200;

/** Returns an i18n error key, or null when the new password is acceptable. */
export function passwordProblem(next: string, confirm: string): string | null {
  if (next.length < PASSWORD_MIN || next.length > PASSWORD_MAX) return "passwordPolicy";
  if (next !== confirm) return "passwordMismatch";
  return null;
}
