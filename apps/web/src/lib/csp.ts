/**
 * Content-Security-Policy for the web origin.
 *
 * script-src: per-request nonce + 'strict-dynamic' (Next 15 stamps the nonce
 * on its bootstrap/inline scripts; chunks it loads inherit trust). No
 * 'unsafe-inline' / 'unsafe-eval' for scripts in production ('unsafe-eval' is
 * added only in `next dev`, which needs it for React Refresh).
 *
 * style-src keeps 'unsafe-inline': React `style={{…}}` attributes and the
 * print sheet's <style> element cannot carry a nonce. Style injection is a
 * far smaller risk than script injection and no third-party origins are
 * allowed anywhere.
 */
export function buildCsp(nonce: string, dev = false): string {
  const directives: Record<string, string> = {
    "default-src": "'self'",
    "script-src": `'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src": "'self' 'unsafe-inline'",
    "img-src": "'self' data: blob:",
    "font-src": "'self' data:",
    "connect-src": dev ? "'self' ws: wss:" : "'self'",
    "object-src": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'",
    "frame-ancestors": "'none'",
    "manifest-src": "'self'",
    "worker-src": "'self' blob:",
  };
  return Object.entries(directives)
    .map(([k, v]) => `${k} ${v}`)
    .join("; ");
}
