"use client";

/**
 * Printable printer test page. `?profile=<id>` uses that profile; without
 * it the clinic's default prescription profile (or plain A4). The `@page`
 * rule comes from the profile, so the browser print preview shows exactly
 * the paper size and margins the clinic configured.
 */
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PrinterTestSheet } from "@/components/PrinterTestSheet";
import { ApiError, api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { onAuthFailure } from "@/lib/session";
import { PrinterDefaults, PrinterProfile, pageCss, pageGeometry } from "@/lib/setup";

function TestView() {
  const { t } = useLang();
  const router = useRouter();
  const search = useSearchParams();
  const id = search.get("profile");
  const [profile, setProfile] = useState<PrinterProfile | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => onAuthFailure(() => router.replace("/login")), [router]);
  useEffect(() => {
    const load = async () => {
      try {
        if (id && /^[0-9a-f-]{36}$/i.test(id)) {
          setProfile(await api.get<PrinterProfile>(`/setup/printers/${id}`));
        } else {
          setProfile((await api.get<PrinterDefaults>("/setup/printers/defaults")).prescription);
        }
      } catch (err) {
        setError(err instanceof ApiError ? String(err.message) : t("loadFailed"));
      }
    };
    void load();
  }, [id, t]);

  if (error) {
    return (
      <main className="print-sheet">
        <p className="error">{error}</p>
      </main>
    );
  }
  if (profile === undefined) {
    return (
      <main className="print-sheet">
        <p className="muted">{t("loading")}</p>
      </main>
    );
  }
  const g = pageGeometry(profile);
  return (
    <main className="print-sheet" data-testid="print-test">
      <PrinterTestSheet geometry={g} profileName={profile?.name ?? t("printerBuiltIn")} />
      <button type="button" className="no-print primary" onClick={() => window.print()} style={{ margin: "1rem auto", display: "block" }}>
        {t("printerPrintTest")}
      </button>
      <p className="no-print muted" style={{ textAlign: "center" }}>
        {t("printersBrowserOnly")}
      </p>
      <style>{`
        .print-sheet { background: #fff; color: #000; margin: 0 auto; padding: 1rem; max-width: 820px; }
        @media print { .no-print { display: none !important; } .print-sheet { padding: 0; } }
        ${pageCss(g)}
      `}</style>
    </main>
  );
}

export default function PrintTestPage() {
  return (
    <Suspense fallback={null}>
      <TestView />
    </Suspense>
  );
}
