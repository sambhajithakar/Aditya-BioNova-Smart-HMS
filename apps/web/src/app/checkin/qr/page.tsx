"use client";

/**
 * Check-in QR for one appointment (`checkin.manage`): create, show, print
 * or share. The QR and the printed slip carry ONLY the random code — no
 * patient name, phone, UHID or diagnosis — plus the clinic's name and the
 * validity date. Creating a new code replaces the previous one.
 */
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { QrSvg } from "@/components/QrSvg";
import { Messages, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { useMe } from "@/lib/me";
import { CheckinIssue, fill, formatCheckinCode } from "@/lib/setup";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function QrBody() {
  const { t } = useLang();
  const me = useMe();
  const search = useSearchParams();
  const appointmentId = search.get("appointment") ?? "";
  const { busy, error, notice, setNotice, act } = useAction();
  const [issued, setIssued] = useState<CheckinIssue | null>(null);

  if (!UUID_RE.test(appointmentId)) {
    return (
      <main className="page">
        <p className="error" role="alert">
          {t("checkinQrNoAppointment")}
        </p>
      </main>
    );
  }

  const create = () =>
    void act(async () => {
      setIssued(await api.post<CheckinIssue>(`/checkin/appointments/${appointmentId}/token`, {}));
    });

  const share = () =>
    void act(async () => {
      if (!issued) return;
      const text = fill(t("checkinShareText"), {
        clinic: me?.organization.name ?? "",
        code: formatCheckinCode(issued.token),
      });
      if (navigator.share) {
        await navigator.share({ text });
      } else {
        await navigator.clipboard.writeText(text);
        setNotice(t("checkinCopied"));
      }
    });

  const validUntil = issued ? new Date(issued.expires_at).toLocaleString() : "";
  return (
    <main className="page">
      <h1 style={{ marginTop: 0 }} className="no-print">
        {t("checkinQrTitle")}
      </h1>
      <p className="muted no-print" style={{ marginTop: 0 }}>
        {t("checkinQrIntro")}
      </p>
      <div className="no-print">
        <Messages error={error} notice={notice} />
      </div>
      {!issued ? (
        <button type="button" className="primary no-print" onClick={create} disabled={busy} data-testid="checkin-qr-create">
          {t("checkinQrCreate")}
        </button>
      ) : (
        <>
          <section className="card qr-slip" data-testid="checkin-qr-slip" style={{ textAlign: "center", maxWidth: 360 }}>
            <p style={{ margin: 0, fontWeight: 700 }}>{me?.organization.name}</p>
            <p style={{ margin: "0.25rem 0" }}>{t("checkinSlipShow")}</p>
            <div style={{ display: "flex", justifyContent: "center" }}>
              <QrSvg value={issued.token} label={t("checkinQrAlt")} />
            </div>
            <p style={{ fontFamily: "monospace", fontSize: "1.1rem", margin: "0.5rem 0 0" }} data-testid="checkin-qr-code">
              {formatCheckinCode(issued.token)}
            </p>
            <p className="muted" style={{ margin: "0.25rem 0 0" }}>
              {t("checkinValidUntil")}: {validUntil}
            </p>
          </section>
          <div className="row no-print" style={{ gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
            <button type="button" className="primary" onClick={() => window.print()}>
              {t("checkinPrintSlip")}
            </button>
            <button type="button" className="secondary" onClick={share} disabled={busy}>
              {t("checkinShare")}
            </button>
            <button type="button" className="ghost" onClick={create} disabled={busy}>
              {t("checkinQrReplace")}
            </button>
          </div>
          <p className="muted no-print" style={{ fontSize: "0.85rem" }}>
            {t("checkinPrivacyNote")}
          </p>
        </>
      )}
      <style>{`
        @media print {
          @page { size: 80mm auto; margin: 4mm; }
          .app-header, .layout-nav, .shell-banner, .no-print { display: none !important; }
          main.page { padding: 0; }
          .qr-slip { border: 0; box-shadow: none; max-width: none !important; }
        }
      `}</style>
    </main>
  );
}

export default function CheckinQrPage() {
  return (
    <AppShell active="checkin">
      <Suspense fallback={null}>
        <QrBody />
      </Suspense>
    </AppShell>
  );
}
