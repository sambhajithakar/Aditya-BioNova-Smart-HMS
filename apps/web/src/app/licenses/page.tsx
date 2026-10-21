/**
 * Open-source licence notices for the web app (M8.1 L2). Public: it holds no
 * user data, and notices must be readable without an account. The Android
 * app has the same information under Settings → Open-source licences.
 */
import Link from "next/link";
import { WEB_COMPONENTS } from "@/lib/licenses";

export const metadata = { title: "Open-source licences — Aditya BioNova Smart HMS" };

export default function LicensesPage() {
  return (
    <main className="page" data-testid="licences">
      <h1 style={{ marginTop: 0 }}>Open-source licences</h1>
      <p>
        Aditya BioNova Smart HMS is proprietary software of Aditya BioNova. It includes the
        third-party components below, which remain under their own licences. Copies of each
        licence ship with the component.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Component</th>
              <th>Version</th>
              <th>Licence</th>
            </tr>
          </thead>
          <tbody>
            {WEB_COMPONENTS.map((c) => (
              <tr key={c.name}>
                <td>
                  {c.name}
                  {c.note && <div className="muted">{c.note}</div>}
                </td>
                <td>{c.version}</td>
                <td>{c.licence}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted">
        The server-side image library sharp and its LGPL-licensed libvips binaries are not shipped:
        the app does no server-side image processing. The Android app lists its own components,
        including Google ML Kit barcode scanning, in Settings → Open-source licences.
      </p>
      <p>
        <Link href="/login">Back to sign-in</Link>
      </p>
    </main>
  );
}
