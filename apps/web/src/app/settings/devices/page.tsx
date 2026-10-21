"use client";

/**
 * Settings → Medical devices (M8.2): the clinic's allow-list of Bluetooth BP
 * monitors and pulse oximeters. Administrators (device.manage) register a
 * device by its Bluetooth address — or a SIM- id for the simulator — and
 * retire it. The address is sent once and stored only as a hash. Readings
 * are captured on the Android app; no device model is validated on hardware
 * yet, and the page says so.
 */
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { useCan } from "@/lib/me";
import { DeviceKind, MedicalDevice, addressKind } from "@/lib/medicalDevices";

function DevicesBody() {
  const { t } = useLang();
  const can = useCan();
  const manage = can("device.manage");
  const [devices, setDevices] = useState<MedicalDevice[]>([]);
  const [form, setForm] = useState({ kind: "bp_monitor" as DeviceKind, label: "", address: "", model: "" });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setDevices(await api.get<MedicalDevice[]>("/devices?include_retired=true"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function register(e: FormEvent) {
    e.preventDefault();
    const kind = addressKind(form.address);
    if (!kind) {
      setError(t("mdAddressInvalid"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.post("/devices", {
        kind: form.kind,
        label: form.label.trim(),
        ble_address: form.address.trim(),
        model: form.model.trim(),
        is_simulator: kind === "simulator",
      });
      setForm({ ...form, label: "", address: "", model: "" });
      setNotice(t("saved"));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function retire(d: MedicalDevice) {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/devices/${d.id}/retire`, {});
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page">
      <h1 style={{ marginTop: 0 }}>{t("mdTitle")}</h1>
      <p>{t("mdIntro")}</p>
      <p className="notice" data-testid="md-not-validated">
        {t("mdNotValidated")}
      </p>
      {error && <p className="error">{error}</p>}
      {notice && <p className="notice">{notice}</p>}

      {manage && (
        <form className="card" onSubmit={(e) => void register(e)} data-testid="md-register">
          <h2 style={{ marginTop: 0 }}>{t("mdRegister")}</h2>
          <div className="field">
            <label htmlFor="md-kind">{t("mdKind")}</label>
            <select
              id="md-kind"
              value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value as DeviceKind })}
            >
              <option value="bp_monitor">{t("mdKind_bp_monitor")}</option>
              <option value="pulse_oximeter">{t("mdKind_pulse_oximeter")}</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="md-label">{t("mdLabel")}</label>
            <input
              id="md-label"
              required
              minLength={2}
              maxLength={80}
              value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="md-address">{t("mdAddress")}</label>
            <input
              id="md-address"
              required
              autoComplete="off"
              value={form.address}
              onChange={(e) => setForm({ ...form, address: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="md-model">{t("mdModel")}</label>
            <input id="md-model" maxLength={80} value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })} />
          </div>
          <button type="submit" disabled={busy}>
            {t("mdRegister")}
          </button>
        </form>
      )}

      <section className="card" style={{ marginTop: "1rem" }}>
        {devices.length === 0 ? (
          <p className="muted">{t("mdNone")}</p>
        ) : (
          <div className="table-wrap">
            <table data-testid="md-list">
              <thead>
                <tr>
                  <th scope="col">{t("mdLabel")}</th>
                  <th scope="col">{t("mdKind")}</th>
                  <th scope="col">{t("mdModel")}</th>
                  <th scope="col" />
                </tr>
              </thead>
              <tbody>
                {devices.map((d) => (
                  <tr key={d.id}>
                    <td>
                      {d.label}{" "}
                      {d.is_simulator && <span className="badge">{t("mdSimulated")}</span>}
                    </td>
                    <td>{t(`mdKind_${d.kind}`)}</td>
                    <td>{d.model || "—"}</td>
                    <td>
                      {d.status === "retired" ? (
                        <span className="muted">{t("mdRetired")}</span>
                      ) : (
                        manage && (
                          <button type="button" className="secondary" disabled={busy}
                            onClick={() => void retire(d)}>
                            {t("mdRetire")}
                          </button>
                        )
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}

export default function MedicalDevicesPage() {
  return (
    <AppShell active="medicalDevices">
      <DevicesBody />
    </AppShell>
  );
}
