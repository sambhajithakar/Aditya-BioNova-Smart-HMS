"use client";

/**
 * Smart Patient QR Check-In (reception, `checkin.manage`).
 *
 * Scan the patient's QR with the device camera (browser `BarcodeDetector`,
 * where available) or type the code. The QR holds only an opaque token; the
 * server answers with minimal context (name + appointment time) so staff can
 * confirm the patient's identity verbally, then issues / confirms the OPD
 * queue token. Second scans are idempotent ("already checked in").
 *
 * Kiosk mode (reception-owned device, staff session): confirms immediately
 * and shows ONLY the queue number — never a name.
 */
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Messages, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import {
  CheckinConfirm,
  CheckinVerify,
  KioskCheckin,
  fill,
  normalizeCheckinCode,
} from "@/lib/setup";

type Detector = { detect: (src: HTMLVideoElement) => Promise<{ rawValue: string }[]> };
type DetectorCtor = {
  new (opts: { formats: string[] }): Detector;
  getSupportedFormats?: () => Promise<string[]>;
};

function barcodeDetector(): DetectorCtor | null {
  if (typeof window === "undefined") return null;
  return ((window as unknown as { BarcodeDetector?: DetectorCtor }).BarcodeDetector ?? null) as DetectorCtor | null;
}

/** Camera + BarcodeDetector loop; calls onCode once per detection. */
function useScanner(onCode: (code: string) => void) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timer = useRef<number | null>(null);
  const [supported, setSupported] = useState<boolean | null>(null);
  const [active, setActive] = useState(false);
  const [camError, setCamError] = useState<string | null>(null);

  useEffect(() => {
    const Ctor = barcodeDetector();
    if (!Ctor || !navigator.mediaDevices?.getUserMedia) {
      setSupported(false);
      return;
    }
    if (Ctor.getSupportedFormats) {
      Ctor.getSupportedFormats()
        .then((f) => setSupported(f.includes("qr_code")))
        .catch(() => setSupported(false));
    } else {
      setSupported(true);
    }
  }, []);

  const stop = useCallback(() => {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
    streamRef.current?.getTracks().forEach((tr) => tr.stop());
    streamRef.current = null;
    setActive(false);
  }, []);

  const start = useCallback(async () => {
    const Ctor = barcodeDetector();
    if (!Ctor) return;
    setCamError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
        audio: false,
      });
      streamRef.current = stream;
      setActive(true);
      const video = videoRef.current;
      if (!video) return;
      video.srcObject = stream;
      await video.play();
      const detector = new Ctor({ formats: ["qr_code"] });
      let busy = false;
      timer.current = window.setInterval(async () => {
        if (busy || !videoRef.current || videoRef.current.readyState < 2) return;
        busy = true;
        try {
          const found = await detector.detect(videoRef.current);
          const value = found.map((f) => normalizeCheckinCode(f.rawValue)).find(Boolean);
          if (value) {
            stop();
            onCode(value);
          }
        } catch {
          /* transient decode errors are normal while aiming */
        } finally {
          busy = false;
        }
      }, 350);
    } catch (err) {
      stop();
      setCamError(err instanceof Error ? err.name : "camera");
    }
  }, [onCode, stop]);

  useEffect(() => stop, [stop]);
  return { videoRef, supported, active, start, stop, camError };
}

function CheckinBody() {
  const { t } = useLang();
  const { busy, error, notice, setError, setNotice, act } = useAction();
  const [kiosk, setKiosk] = useState(false);
  const [code, setCode] = useState("");
  const [verified, setVerified] = useState<{ code: string; info: CheckinVerify } | null>(null);
  const [done, setDone] = useState<CheckinConfirm | null>(null);
  const [kioskResult, setKioskResult] = useState<KioskCheckin | null>(null);
  const resetTimer = useRef<number | null>(null);

  const reset = useCallback(() => {
    setVerified(null);
    setDone(null);
    setKioskResult(null);
    setCode("");
    setError(null);
    setNotice(null);
  }, [setError, setNotice]);

  const submitCode = useCallback(
    (raw: string) => {
      const norm = normalizeCheckinCode(raw);
      setDone(null);
      setKioskResult(null);
      if (!norm) {
        setError(t("checkinBadCode"));
        return;
      }
      void act(async () => {
        if (kiosk) {
          try {
            const r = await api.post<KioskCheckin>("/checkin/kiosk", { code: norm });
            setKioskResult(r);
          } finally {
            setCode("");
            if (resetTimer.current) window.clearTimeout(resetTimer.current);
            resetTimer.current = window.setTimeout(reset, 10_000);
          }
          return;
        }
        const info = await api.post<CheckinVerify>("/checkin/verify", { code: norm });
        setVerified({ code: norm, info });
      });
    },
    [act, kiosk, reset, setError, t],
  );

  const scanner = useScanner(submitCode);
  useEffect(() => () => {
    if (resetTimer.current) window.clearTimeout(resetTimer.current);
  }, []);

  const confirm = () =>
    void act(async () => {
      if (!verified) return;
      const r = await api.post<CheckinConfirm>("/checkin/confirm", { code: verified.code });
      setDone(r);
      setVerified(null);
      setCode("");
    });

  const onManual = (e: FormEvent) => {
    e.preventDefault();
    submitCode(code);
  };

  const cameraBlock = (
    <div style={{ marginBottom: "1rem" }}>
      {scanner.supported === false && <p className="muted">{t("checkinNoCamera")}</p>}
      {scanner.supported && (
        <>
          <video
            ref={scanner.videoRef}
            muted
            playsInline
            aria-label={t("checkinCamera")}
            style={{
              width: "100%",
              maxWidth: 420,
              display: scanner.active ? "block" : "none",
              borderRadius: 8,
              background: "#000",
            }}
          />
          {scanner.active ? (
            <button type="button" className="secondary" onClick={scanner.stop}>
              {t("checkinStopCamera")}
            </button>
          ) : (
            <button type="button" className="primary" onClick={() => void scanner.start()} data-testid="checkin-scan">
              {t("checkinScan")}
            </button>
          )}
          {scanner.camError && <p className="error">{fill(t("checkinCameraError"), { reason: scanner.camError })}</p>}
        </>
      )}
    </div>
  );

  const manualForm = (
    <form onSubmit={onManual} className="row" style={{ gap: "0.5rem", flexWrap: "wrap", alignItems: "end" }}>
      <label className="field" style={{ flex: "1 1 18rem" }}>
        {t("checkinCodeLabel")}
        <input
          type="text"
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="ABCD EFGH IJKL MNOP QRST UVWX YZ"
          data-testid="checkin-code"
          style={{ fontFamily: "monospace", letterSpacing: "0.05em" }}
        />
      </label>
      <button className="primary" type="submit" disabled={busy || !code.trim()} data-testid="checkin-lookup">
        {kiosk ? t("checkinKioskGo") : t("checkinLookup")}
      </button>
    </form>
  );

  if (kiosk) {
    return (
      <main className="page" data-testid="checkin-kiosk">
        <section className="card" style={{ textAlign: "center", fontSize: "1.15rem" }}>
          <h1 style={{ marginTop: 0 }}>{t("checkinKioskTitle")}</h1>
          <p>{t("checkinKioskIntro")}</p>
          {kioskResult ? (
            <div role="status" aria-live="assertive" data-testid="kiosk-result">
              <p style={{ fontSize: "1.4rem", margin: "0.5rem 0" }}>
                {kioskResult.status === "checked_in" ? t("checkinKioskDone") : t("checkinKioskAlready")}
              </p>
              <p style={{ fontSize: "4rem", fontWeight: 800, margin: 0 }}>{kioskResult.token_number}</p>
              <p className="muted">{t("checkinKioskToken")}</p>
              <button type="button" className="secondary" onClick={reset}>
                {t("checkinNext")}
              </button>
            </div>
          ) : (
            <>
              {cameraBlock}
              {manualForm}
            </>
          )}
          {error && (
            <p className="error" role="alert">
              {t("checkinKioskError")}
            </p>
          )}
        </section>
        <p className="muted" style={{ fontSize: "0.85rem" }}>{t("checkinKioskStaffNote")}</p>
        <button type="button" className="ghost" onClick={() => { reset(); setKiosk(false); }}>
          {t("checkinExitKiosk")}
        </button>
      </main>
    );
  }

  return (
    <main className="page" data-testid="checkin-page">
      <h1 style={{ marginTop: 0 }}>{t("checkinTitle")}</h1>
      <p className="muted" style={{ marginTop: 0 }}>{t("checkinIntro")}</p>
      <Messages error={error} notice={notice} />

      <section className="card">
        {cameraBlock}
        {manualForm}
      </section>

      {verified && (
        <section className="card" style={{ marginTop: "1rem" }} data-testid="checkin-verified">
          <h2 style={{ marginTop: 0 }}>{t("checkinConfirmIdentity")}</h2>
          <p style={{ fontSize: "1.3rem", margin: "0.25rem 0" }}>
            <strong data-testid="checkin-patient">{verified.info.patient_display_name}</strong>
          </p>
          <p style={{ margin: "0.25rem 0" }}>
            {t("checkinApptAt")}: {new Date(verified.info.appointment_starts_at).toLocaleString()} ·{" "}
            {verified.info.branch_name}
          </p>
          <p className="muted">{t("checkinAskPatient")}</p>
          {verified.info.status === "already_checked_in" ? (
            <p className="notice" role="status">
              {fill(t("checkinAlready"), { n: verified.info.queue_token_number ?? "—" })}
            </p>
          ) : (
            <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
              <button type="button" className="primary" onClick={confirm} disabled={busy} data-testid="checkin-confirm">
                {t("checkinConfirm")}
              </button>
              <button type="button" className="secondary" onClick={reset} disabled={busy}>
                {t("cancel")}
              </button>
            </div>
          )}
        </section>
      )}

      {done && (
        <section className="card" style={{ marginTop: "1rem", textAlign: "center" }} role="status" data-testid="checkin-done">
          <p style={{ margin: 0 }}>
            {done.status === "checked_in" ? t("checkinDone") : t("checkinAlreadyShort")}
          </p>
          <p style={{ fontSize: "3rem", fontWeight: 800, margin: "0.25rem 0" }} data-testid="checkin-token">
            {done.queue_entry.token_number}
          </p>
          <p className="muted" style={{ margin: 0 }}>{t("checkinQueueToken")}</p>
          <button type="button" className="secondary" onClick={reset} style={{ marginTop: "0.5rem" }}>
            {t("checkinNext")}
          </button>
        </section>
      )}

      <section className="card" style={{ marginTop: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>{t("checkinKioskTitle")}</h3>
        <p className="muted" style={{ marginTop: 0 }}>{t("checkinKioskStaffNote")}</p>
        <button type="button" className="secondary" onClick={() => { reset(); setKiosk(true); }} data-testid="checkin-kiosk-mode">
          {t("checkinStartKiosk")}
        </button>
      </section>
      <p className="muted" style={{ fontSize: "0.85rem" }}>{t("checkinPrivacyNote")}</p>
    </main>
  );
}

export default function CheckinPage() {
  return (
    <AppShell active="checkin">
      <CheckinBody />
    </AppShell>
  );
}
