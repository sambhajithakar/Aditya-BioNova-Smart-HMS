"use client";

/**
 * Organization profile (M7.1): legal / contact details used on letterheads
 * and invoices, the default UI language, and the MFA policy (which roles
 * must enrol two-step verification). Reading needs org.read; changes need
 * org.manage (owner / admin) — the form is read-only otherwise.
 *
 * GSTIN and PIN code are validated client-side with the same regexes the
 * API enforces.
 */
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Messages, fmtDateTime, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { LANGS } from "@/lib/i18n";
import { useLang } from "@/lib/lang";
import { useCan } from "@/lib/me";
import { notifyMeChanged } from "@/lib/session";
import {
  MFA_POLICY_ROLES,
  OrganizationProfile,
  isValidGstin,
  isValidPincode,
  normalizeGstin,
  serverMessage,
} from "@/lib/saas";

const TEXT_FIELDS = [
  ["name", "orgName"],
  ["legal_name", "legalName"],
  ["address_line1", "addressLine1"],
  ["address_line2", "addressLine2"],
  ["city", "city"],
  ["state", "stateName"],
  ["pincode", "pincode"],
  ["phone", "orgPhone"],
  ["email", "orgEmail"],
  ["gstin", "gstin"],
  ["registration_number", "orgRegistrationNumber"],
  ["timezone", "timezone"],
] as const;

type FieldKey = (typeof TEXT_FIELDS)[number][0];
type Form = Record<FieldKey, string> & { letterhead_note: string; default_language: string };

function toForm(o: OrganizationProfile): Form {
  const f = {} as Form;
  for (const [k] of TEXT_FIELDS) f[k] = (o[k] as string | null) ?? "";
  f.letterhead_note = o.letterhead_note ?? "";
  f.default_language = o.default_language ?? "en";
  return f;
}

function OrganizationBody() {
  const { t } = useLang();
  const can = useCan();
  const manage = can("org.manage");
  const { busy, error, notice, setError, setNotice, act } = useAction();
  const [org, setOrg] = useState<OrganizationProfile | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [roles, setRoles] = useState<string[]>([]);
  const [touched, setTouched] = useState(false);

  const load = useCallback(async () => {
    try {
      const o = await api.get<OrganizationProfile>("/organization");
      setOrg(o);
      setForm(toForm(o));
      setRoles(o.mfa_required_roles ?? []);
    } catch (err) {
      setError(serverMessage(err, t("loadFailed")));
    }
  }, [setError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!form || !org) {
    return (
      <main className="page">
        <h1 style={{ marginTop: 0 }}>{t("orgProfile")}</h1>
        <Messages error={error} notice={notice} />
        {!error && <p className="muted">{t("loading")}</p>}
      </main>
    );
  }

  const gstinBad = !isValidGstin(normalizeGstin(form.gstin));
  const pinBad = !isValidPincode(form.pincode);

  const set = (k: keyof Form, v: string) => setForm({ ...form, [k]: v });

  const onSave = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (gstinBad || pinBad) {
      setError(gstinBad ? t("invalidGstin") : t("invalidPincode"));
      return;
    }
    const body: Record<string, unknown> = {};
    for (const [k] of TEXT_FIELDS) {
      const v = k === "gstin" ? normalizeGstin(form[k]) : form[k].trim();
      body[k] = v === "" && k !== "name" ? null : v;
    }
    body.letterhead_note = form.letterhead_note.trim() || null;
    body.default_language = form.default_language;
    void act(async () => {
      const o = await api.patch<OrganizationProfile>("/organization", body);
      setOrg(o);
      setForm(toForm(o));
      setNotice(t("saved"));
      notifyMeChanged();
    });
  };

  const onSavePolicy = (e: FormEvent) => {
    e.preventDefault();
    void act(async () => {
      const o = await api.patch<OrganizationProfile>("/organization", {
        mfa_required_roles: roles,
      });
      setOrg(o);
      setRoles(o.mfa_required_roles ?? []);
      setNotice(t("saved"));
      // the policy may now apply to the current user
      notifyMeChanged();
    });
  };

  const toggleRole = (r: string) =>
    setRoles(roles.includes(r) ? roles.filter((x) => x !== r) : [...roles, r]);

  return (
    <main className="page">
      <h1 style={{ marginTop: 0 }}>{t("orgProfile")}</h1>
      <Messages error={error} notice={notice} />
      {!manage && <p className="notice">{t("readOnlyView")}</p>}

      <section className="card">
        <p className="muted" style={{ marginTop: 0 }}>
          {t("slug")}: <strong>{org.slug}</strong> · {t("status")}: <strong>{t(org.status)}</strong> ·{" "}
          {t("createdAt")}: {fmtDateTime(org.created_at)}
        </p>
        <form onSubmit={onSave} noValidate>
          <fieldset disabled={!manage || busy} style={{ border: 0, padding: 0, margin: 0 }}>
            <div className="grid two">
              {TEXT_FIELDS.map(([k, label]) => {
                const invalid =
                  (k === "gstin" && gstinBad && (touched || form.gstin.length >= 15)) ||
                  (k === "pincode" && pinBad && (touched || form.pincode.length >= 6));
                return (
                  <label className="field" key={k}>
                    {t(label)}
                    <input
                      type={k === "email" ? "email" : "text"}
                      name={k}
                      value={form[k]}
                      onChange={(e) => set(k, e.target.value)}
                      onBlur={() => (k === "gstin" || k === "pincode") && setTouched(true)}
                      required={k === "name"}
                      maxLength={k === "gstin" ? 15 : k === "pincode" ? 6 : 200}
                      inputMode={k === "pincode" || k === "phone" ? "numeric" : undefined}
                      autoCapitalize={k === "gstin" ? "characters" : undefined}
                      aria-invalid={invalid || undefined}
                      aria-describedby={invalid ? `${k}-err` : undefined}
                    />
                    {invalid && (
                      <span className="field-error" id={`${k}-err`}>
                        {k === "gstin" ? t("invalidGstin") : t("invalidPincode")}
                      </span>
                    )}
                  </label>
                );
              })}
              <label className="field">
                {t("defaultLanguage")}
                <select
                  value={form.default_language}
                  onChange={(e) => set("default_language", e.target.value)}
                >
                  {LANGS.map((l) => (
                    <option key={l.code} value={l.code}>
                      {l.native}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="field" style={{ marginTop: "1rem" }}>
              {t("letterheadNote")}
              <textarea
                className="wide"
                rows={3}
                maxLength={500}
                value={form.letterhead_note}
                onChange={(e) => set("letterhead_note", e.target.value)}
              />
            </label>
            {manage && (
              <button type="submit" className="primary" style={{ marginTop: "1rem" }}>
                {t("save")}
              </button>
            )}
          </fieldset>
        </form>
      </section>

      <section className="card" style={{ marginTop: "1.25rem" }} id="mfa-policy">
        <h2 style={{ marginTop: 0 }}>{t("mfaPolicy")}</h2>
        <p className="muted">{t("mfaPolicyHint")}</p>
        <form onSubmit={onSavePolicy}>
          <fieldset className="check-grid" disabled={!manage || busy}>
            <legend className="sr-only">{t("mfaPolicy")}</legend>
            {MFA_POLICY_ROLES.map((r) => (
              <label key={r}>
                <input
                  type="checkbox"
                  checked={roles.includes(r)}
                  onChange={() => toggleRole(r)}
                />
                {t(`role_${r}`)}
              </label>
            ))}
          </fieldset>
          {manage && (
            <>
              <p className="warn-box">{t("mfaPolicyOwnerWarn")}</p>
              <button type="submit" className="primary" disabled={busy}>
                {t("savePolicy")}
              </button>
            </>
          )}
        </form>
      </section>
    </main>
  );
}

export default function OrganizationPage() {
  return (
    <AppShell active="organization">
      <OrganizationBody />
    </AppShell>
  );
}
