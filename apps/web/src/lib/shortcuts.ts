/**
 * Desktop keyboard shortcuts (pure parser; the shell owns the listener).
 *
 *   /  or Ctrl/⌘+K   focus the quick patient search
 *   g then <key>     go to a module (see GOTO) — "g" must be followed by
 *                    the second key within CHORD_TIMEOUT_MS
 *   n                the current page's primary "new" action, if it has one
 *   ?                open the shortcuts help dialog
 *   Esc              close the dialog / sheet (handled by the dialog itself)
 *
 * Single-key shortcuts never fire while the user is typing in an input,
 * textarea, select or contenteditable element, nor with Alt/Ctrl/⌘ held
 * (so browser and OS shortcuts keep working). Ctrl/⌘+K is the one shortcut
 * that also works inside fields, because it cannot be typed by accident.
 */

export const CHORD_TIMEOUT_MS = 1200;

/** Second key of a "g" chord → nav item key (lib/nav.ts). */
export const GOTO: Record<string, string> = {
  d: "dashboard",
  p: "patients",
  a: "appointments",
  q: "queue",
  c: "consultation",
  b: "billing",
  f: "pharmacy",
  l: "lab",
  i: "ipd",
  r: "reports",
};

export type ShortcutAction =
  | { type: "focusSearch" }
  | { type: "help" }
  | { type: "new" }
  | { type: "goto"; nav: string };

export type KeyLike = {
  key: string;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
  shiftKey?: boolean;
  /** true when the event target is an editable field */
  editable?: boolean;
  /** true while an IME composition is in progress */
  isComposing?: boolean;
  repeat?: boolean;
};

export type ChordState = { pendingG: number | null };

export const initialChord: ChordState = { pendingG: null };

/** Is this element one the user types into? */
export function isEditableTarget(el: EventTarget | null): boolean {
  if (!el || typeof (el as HTMLElement).tagName !== "string") return false;
  const node = el as HTMLElement;
  const tag = node.tagName.toLowerCase();
  if (tag === "textarea" || tag === "select") return true;
  if (tag === "input") {
    const type = ((node as HTMLInputElement).type || "text").toLowerCase();
    return !["button", "submit", "reset", "checkbox", "radio", "range", "color", "file", "image"].includes(type);
  }
  return node.isContentEditable === true || node.getAttribute?.("contenteditable") === "true";
}

/**
 * Resolve one keydown. Returns the action (if any) and the next chord
 * state. Pure: `now` is passed in so tests control time.
 */
export function resolveShortcut(
  e: KeyLike,
  state: ChordState,
  now: number,
): { action: ShortcutAction | null; state: ChordState } {
  const none = { action: null, state: initialChord };
  if (e.isComposing || e.repeat) return { action: null, state };

  // Ctrl/⌘+K: everywhere, including inside fields.
  if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k") {
    return { action: { type: "focusSearch" }, state: initialChord };
  }
  if (e.ctrlKey || e.metaKey || e.altKey) return none;
  if (e.editable) return none;

  const key = e.key;
  const chordLive = state.pendingG !== null && now - state.pendingG <= CHORD_TIMEOUT_MS;
  if (chordLive) {
    const nav = GOTO[key.toLowerCase()];
    return { action: nav ? { type: "goto", nav } : null, state: initialChord };
  }
  if (key === "g" || key === "G") return { action: null, state: { pendingG: now } };
  if (key === "/") return { action: { type: "focusSearch" }, state: initialChord };
  if (key === "?") return { action: { type: "help" }, state: initialChord };
  if (key === "n" || key === "N") return { action: { type: "new" }, state: initialChord };
  return none;
}

/**
 * "n" target per page: the first field of the page's primary create form
 * (focus only — never submits). A page can also mark any element with
 * data-shortcut="new", which takes precedence.
 */
export const NEW_TARGETS: Record<string, string> = {
  "/patients": "#full_name",
  "/appointments": "#apq-q",
  "/consultation": "#cp-q",
  "/billing": "#bi-p-q",
  "/expenses": "#ec",
};

export function newTargetSelectors(pathname: string | null): string[] {
  const mapped = pathname ? NEW_TARGETS[pathname] : undefined;
  return mapped ? ['[data-shortcut="new"]', mapped] : ['[data-shortcut="new"]'];
}

/** Rows for the help dialog: [keys, i18n label key, nav key?]. */
export const SHORTCUT_HELP: { keys: string[]; label: string; nav?: string }[] = [
  { keys: ["/"], label: "devScSearch" },
  { keys: ["Ctrl", "K"], label: "devScSearch" },
  { keys: ["n"], label: "devScNew" },
  { keys: ["?"], label: "devScHelp" },
  { keys: ["Esc"], label: "devScClose" },
  ...Object.entries(GOTO).map(([k, nav]) => ({ keys: ["g", k], label: "devScGoto", nav })),
];
