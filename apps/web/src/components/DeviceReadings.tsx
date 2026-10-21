"use client";

/**
 * Clinician review of Bluetooth device readings for one consultation (M8.2).
 *
 * Readings captured on the Android app wait here as "pending review". A
 * clinician accepts one only after ticking that it belongs to this patient
 * and was measured just now; the API then records it through the normal
 * vitals path (same validation and audit). Rejecting needs a reason.
 * Simulated readings carry a SIMULATED badge. Nothing is accepted
 * automatically, and reviewing needs a connection.
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { DeviceReading, originalUnitNote, readingSummary } from "@/lib/medicalDevices";

export function DeviceReadingsPanel({
  encounterId,
  patientLabel,
  canReview,
  onAccepted,
}: {
  encounterId: string;
  patientLabel: string;
  canReview: boolean;
  onAccepted: () => void;
}) {
  const { t } = useLang();
  const [pending, setPending] = useState<DeviceReading[]>([]);
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      setPending(
        await api.get<DeviceReading[]>(
          `/device-readings?encounter_id=${encounterId}&status=pending_review`,
        ),
      );
    } catch {
      setPending([]);
    }
  }, [encounterId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function decide(r: DeviceReading, accept: boolean) {
    if (!accept && (reasons[r.id] ?? "").trim().length < 3) {
      setMessage({ ok: false, text: t("mdReasonRequired") });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      if (accept) {
        await api.post(`/device-readings/${r.id}/accept`, { surface: "web", confirm_patient: true });
        onAccepted();
      } else {
        await api.post(`/device-readings/${r.id}/reject`, {
          surface: "web",
          reason: (reasons[r.id] ?? "").trim(),
        });
      }
      setMessage({ ok: true, text: accept ? t("mdAccepted") : t("mdRejected") });
      await load();
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  }

  if (pending.length === 0 && !message) {
    return (
      <p className="muted" data-testid="device-readings-none">
        {t("mdReviewNone")}
      </p>
    );
  }
  return (
    <div data-testid="device-readings">
      <h4 style={{ marginBottom: "0.25rem" }}>{t("mdReviewTitle")}</h4>
      {message && (
        <p role="status" className={message.ok ? "notice" : "error"}>
          {message.text}
        </p>
      )}
      {pending.map((r) => {
        const unitNote = originalUnitNote(r);
        return (
          <div key={r.id} className="card" style={{ padding: "0.6rem", marginBottom: "0.5rem" }}>
            <div>
              <strong>{readingSummary(r)}</strong>
              {r.device_is_simulator && (
                <span className="badge" data-testid="reading-simulated" style={{ marginLeft: "0.5rem" }}>
                  {t("mdSimulated")}
                </span>
              )}
            </div>
            <div className="muted">
              {r.device_label} · {t("mdCaptured")} {new Date(r.captured_at).toLocaleString()}
              {unitNote ? ` · ${unitNote}` : ""}
            </div>
            {r.flags.length > 0 && (
              <div data-testid="reading-flags">
                {t("mdFlags")}: {r.flags.join(", ")}
              </div>
            )}
            {r.clock_skew && <div className="muted">{t("mdClockSkew")}</div>}
            <div className="muted">{t("mdNotRecord")}</div>
            {canReview && (
              <div style={{ display: "grid", gap: "0.4rem", marginTop: "0.4rem" }}>
                <label>
                  <input
                    type="checkbox"
                    data-testid={`confirm-${r.id}`}
                    checked={confirmed[r.id] ?? false}
                    onChange={(e) => setConfirmed((c) => ({ ...c, [r.id]: e.target.checked }))}
                  />{" "}
                  {t("mdConfirm").replace("{patient}", patientLabel)}
                </label>
                <button
                  type="button"
                  data-testid={`accept-${r.id}`}
                  disabled={busy || !confirmed[r.id]}
                  onClick={() => void decide(r, true)}
                >
                  {t("mdAccept")}
                </button>
                <input
                  aria-label={t("mdReason")}
                  placeholder={t("mdReason")}
                  data-testid={`reason-${r.id}`}
                  value={reasons[r.id] ?? ""}
                  onChange={(e) => setReasons((x) => ({ ...x, [r.id]: e.target.value }))}
                />
                <button
                  type="button"
                  className="secondary"
                  data-testid={`reject-${r.id}`}
                  disabled={busy}
                  onClick={() => void decide(r, false)}
                >
                  {t("mdReject")}
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
