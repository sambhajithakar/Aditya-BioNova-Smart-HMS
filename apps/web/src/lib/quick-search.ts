/**
 * Hand-off from the shell's quick patient search to the Patients page.
 *
 * The search term is passed IN MEMORY (module state), never through the URL
 * or Web Storage: a patient's name or phone number must not end up in
 * browser history, server logs or storage.
 */
export type PatientSearchRequest = { q: string };

let pending: PatientSearchRequest | null = null;
const listeners = new Set<(r: PatientSearchRequest) => void>();

/** Ask the Patients page to run (and focus) a search. */
export function requestPatientSearch(q: string): void {
  const req = { q: q.trim() };
  if (listeners.size > 0) {
    for (const l of listeners) l(req);
    pending = null;
  } else {
    pending = req; // picked up when the Patients page mounts
  }
}

/** Patients page on mount: take a request queued before it rendered. */
export function consumePatientSearch(): PatientSearchRequest | null {
  const r = pending;
  pending = null;
  return r;
}

/** Patients page while mounted: receive requests directly. */
export function onPatientSearch(l: (r: PatientSearchRequest) => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** Small debounce helper (used by search-as-you-type inputs). */
export function debounce<A extends unknown[]>(fn: (...a: A) => void, ms: number) {
  let timer: ReturnType<typeof setTimeout> | null = null;
  const d = (...a: A) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      fn(...a);
    }, ms);
  };
  d.cancel = () => {
    if (timer) clearTimeout(timer);
    timer = null;
  };
  return d;
}
