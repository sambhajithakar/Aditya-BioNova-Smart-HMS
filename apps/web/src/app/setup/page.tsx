"use client";

/**
 * BioNova Smart Setup Wizard (owner / admin, `setup.manage`).
 *
 * Plain-language, one step at a time, defaults pre-filled, every step can be
 * skipped and revisited; progress is saved on the server
 * (`/setup/wizard`) so it resumes on any device. Steps reuse the existing
 * APIs where they exist (organization profile, branches, invitations,
 * subscription) and the new `/setup/*` endpoints for the rest. The edition
 * step is read-only — no payment happens here.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, ReactNode, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Messages, useAction } from "@/components/Saas";
import { ApiError, Branch, Member, api } from "@/lib/api";
import { LANGS, Lang } from "@/lib/i18n";
import { useLang } from "@/lib/lang";
import { useCan } from "@/lib/me";
import { notifyMeChanged } from "@/lib/session";
import {
  OrganizationProfile,
  SubscriptionOut,
  isValidGstin,
  normalizeGstin,
  serverMessage,
} from "@/lib/saas";
import {
  BillingSettings,
  FeesOut,
  OrgSettingsDoc,
  OrgSettingsOut,
  PAYMENT_METHODS,
  PRINTER_KINDS,
  PrescriptionSettings,
  PrinterKind,
  PrinterProfile,
  SLOT_LENGTHS,
  ScheduleSettings,
  WIZARD_STEPS,
  WizardState,
  WizardStepKey,
  WorkingHoursOut,
  WorkingSession,
  cleanSessions,
  defaultWeek,
  feeInput,
  fill,
  hhmm,
  neighbourStep,
  parseFee,
  resumeStep,
  workingHoursErrors,
} from "@/lib/setup";

type StepProps = {
  /** Persist the step's data, then mark it done and move on. */
  onSaved: () => Promise<void>;
  busy: boolean;
  act: (fn: () => Promise<void>) => Promise<boolean>;
  setError: (e: string | null) => void;
};

function StepFrame({
  title,
  intro,
  children,
  onSubmit,
  busy,
  submitLabel,
}: {
  title: string;
  intro: string;
  children: ReactNode;
  onSubmit: (e: FormEvent) => void;
  busy: boolean;
  submitLabel?: string;
}) {
  const { t } = useLang();
  return (
    <form onSubmit={onSubmit} noValidate data-testid="wizard-step-form">
      <h2 style={{ marginTop: 0 }}>{title}</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        {intro}
      </p>
      <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0 }}>
        {children}
        <div className="row" style={{ marginTop: "1rem", gap: "0.5rem", flexWrap: "wrap" }}>
          <button className="primary" type="submit" data-testid="wizard-save">
            {submitLabel ?? t("wizSaveContinue")}
          </button>
        </div>
      </fieldset>
    </form>
  );
}

// --- steps ------------------------------------------------------------------------------
function IdentityStep({ onSaved, busy, act, setError }: StepProps) {
  const { t } = useLang();
  const [f, setF] = useState({ name: "", address_line1: "", city: "", phone: "", registration_number: "", gstin: "" });
  useEffect(() => {
    api
      .get<OrganizationProfile>("/organization")
      .then((o) =>
        setF({
          name: o.name ?? "",
          address_line1: o.address_line1 ?? "",
          city: o.city ?? "",
          phone: o.phone ?? "",
          registration_number: o.registration_number ?? "",
          gstin: o.gstin ?? "",
        }),
      )
      .catch(() => undefined);
  }, []);
  const set = (k: keyof typeof f, v: string) => setF({ ...f, [k]: v });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const gstin = normalizeGstin(f.gstin);
    if (!isValidGstin(gstin)) {
      setError(t("invalidGstin"));
      return;
    }
    void act(async () => {
      const body: Record<string, string | null> = {};
      for (const [k, v] of Object.entries({ ...f, gstin })) body[k] = v.trim() === "" && k !== "name" ? null : v.trim();
      await api.patch("/organization", body);
      notifyMeChanged();
      await onSaved();
    });
  };
  const field = (k: keyof typeof f, label: string, hint?: string, type = "text") => (
    <label className="field" key={k}>
      {label}
      <input type={type} value={f[k]} onChange={(e) => set(k, e.target.value)} data-testid={`wiz-${k}`} />
      {hint && <span className="muted" style={{ fontWeight: 400, fontSize: "0.85rem" }}>{hint}</span>}
    </label>
  );
  return (
    <StepFrame title={t("wizStep_identity")} intro={t("wizIdentityIntro")} onSubmit={submit} busy={busy}>
      <div className="grid two">
        {field("name", t("orgName"))}
        {field("phone", t("orgPhone"), t("wizPhoneHint"), "tel")}
        {field("address_line1", t("addressLine1"))}
        {field("city", t("city"))}
        {field("registration_number", t("orgRegistrationNumber"), t("wizOptional"))}
        {field("gstin", t("gstin"), t("wizOptional"))}
      </div>
    </StepFrame>
  );
}

function BranchStep({ onSaved, busy, act }: StepProps) {
  const { t } = useLang();
  const [branches, setBranches] = useState<Branch[]>([]);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const load = useCallback(() => api.get<Branch[]>("/branches").then(setBranches).catch(() => undefined), []);
  useEffect(() => {
    void load();
  }, [load]);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void act(async () => {
      if (name.trim()) {
        await api.post("/branches", { name: name.trim(), code: code.trim() || "MAIN" });
        setName("");
        setCode("");
        await load();
      }
      await onSaved();
    });
  };
  return (
    <StepFrame title={t("wizStep_branch")} intro={t("wizBranchIntro")} onSubmit={submit} busy={busy}>
      {branches.length > 0 ? (
        <ul>
          {branches.map((b) => (
            <li key={b.id}>
              <strong>{b.name}</strong> ({b.code}) — {t(b.status)}
            </li>
          ))}
        </ul>
      ) : (
        <p className="notice">{t("wizNoBranchYet")}</p>
      )}
      <div className="grid two">
        <label className="field">
          {t("wizBranchName")}
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder={t("wizBranchNameHint")} />
        </label>
        <label className="field">
          {t("wizBranchCode")}
          <input type="text" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="MAIN" />
        </label>
      </div>
    </StepFrame>
  );
}

const STAFF_ROLES = ["doctor", "nurse", "receptionist", "pharmacist", "lab_technician", "billing"] as const;

function StaffStep({ onSaved, busy, act, setError }: StepProps) {
  const { t } = useLang();
  const [rows, setRows] = useState([
    { email: "", role_key: "doctor" },
    { email: "", role_key: "receptionist" },
    { email: "", role_key: "nurse" },
  ]);
  const [members, setMembers] = useState<Member[]>([]);
  const [sent, setSent] = useState<string[]>([]);
  useEffect(() => {
    api.get<Member[]>("/members").then(setMembers).catch(() => undefined);
  }, []);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const filled = rows.filter((r) => r.email.trim());
    const bad = filled.find((r) => !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(r.email.trim()));
    if (bad) {
      setError(fill(t("wizBadEmail"), { email: bad.email }));
      return;
    }
    void act(async () => {
      const done: string[] = [];
      const failed: string[] = [];
      for (const r of filled) {
        try {
          await api.post("/members/invitations", { email: r.email.trim(), role_key: r.role_key });
          done.push(r.email.trim());
        } catch (err) {
          failed.push(`${r.email.trim()}: ${serverMessage(err, t("actionFailed"))}`);
        }
      }
      setSent([...sent, ...done]);
      setRows(rows.map((r) => (done.includes(r.email.trim()) ? { ...r, email: "" } : r)));
      if (failed.length) throw new ApiError(400, failed.join("; "));
      await onSaved();
    });
  };
  return (
    <StepFrame title={t("wizStep_staff")} intro={t("wizStaffIntro")} onSubmit={submit} busy={busy}>
      <p className="muted">{fill(t("wizStaffCount"), { n: members.length })}</p>
      {rows.map((r, i) => (
        <div className="row" key={i} style={{ gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          <label className="field" style={{ flex: "2 1 14rem" }}>
            {t("email")}
            <input
              type="email"
              value={r.email}
              onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, email: e.target.value } : x)))}
              data-testid={`wiz-staff-email-${i}`}
            />
          </label>
          <label className="field" style={{ flex: "1 1 10rem" }}>
            {t("role")}
            <select
              value={r.role_key}
              onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, role_key: e.target.value } : x)))}
            >
              {STAFF_ROLES.map((k) => (
                <option key={k} value={k}>
                  {t(`role_${k}`)}
                </option>
              ))}
            </select>
          </label>
        </div>
      ))}
      <button
        type="button"
        className="secondary"
        onClick={() => setRows([...rows, { email: "", role_key: "doctor" }])}
        disabled={rows.length >= 10}
      >
        {t("wizAddRow")}
      </button>
      {sent.length > 0 && <p className="notice">{fill(t("wizInvitesSent"), { list: sent.join(", ") })}</p>}
      <p className="muted" style={{ fontSize: "0.85rem" }}>{t("wizStaffNote")}</p>
    </StepFrame>
  );
}

function LanguageStep({ onSaved, busy, act }: StepProps) {
  const { t, setLang } = useLang();
  const [lang, setL] = useState<Lang>("en");
  useEffect(() => {
    api
      .get<OrganizationProfile>("/organization")
      .then((o) => setL((o.default_language as Lang) ?? "en"))
      .catch(() => undefined);
  }, []);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void act(async () => {
      await api.patch("/organization", { default_language: lang });
      setLang(lang);
      notifyMeChanged();
      await onSaved();
    });
  };
  return (
    <StepFrame title={t("wizStep_language")} intro={t("wizLanguageIntro")} onSubmit={submit} busy={busy}>
      <div role="radiogroup" className="row" style={{ gap: "0.75rem", flexWrap: "wrap" }}>
        {LANGS.map((l) => (
          <label key={l.code} className="card" style={{ padding: "0.75rem 1rem", cursor: "pointer" }}>
            <input type="radio" name="lang" checked={lang === l.code} onChange={() => setL(l.code)} />{" "}
            <strong style={{ fontSize: "1.15rem" }}>{l.native}</strong>
          </label>
        ))}
      </div>
    </StepFrame>
  );
}

function WorkingHoursStep({ onSaved, busy, act, setError }: StepProps) {
  const { t } = useLang();
  const [branches, setBranches] = useState<Branch[]>([]);
  const [branchId, setBranchId] = useState("");
  const [days, setDays] = useState<Record<number, WorkingSession | null>>({});
  useEffect(() => {
    api
      .get<Branch[]>("/branches")
      .then((bs) => {
        const active = bs.filter((b) => b.status === "active");
        setBranches(active);
        if (active[0]) setBranchId(active[0].id);
      })
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    if (!branchId) return;
    api
      .get<WorkingHoursOut>(`/setup/branches/${branchId}/working-hours`)
      .then((h) => {
        const source = h.sessions.length ? h.sessions : defaultWeek();
        const map: Record<number, WorkingSession | null> = {};
        for (let d = 0; d < 7; d++) map[d] = source.find((s) => s.weekday === d) ?? null;
        setDays(map);
      })
      .catch(() => undefined);
  }, [branchId]);
  const update = (d: number, patch: Partial<WorkingSession>) =>
    setDays({ ...days, [d]: { ...(days[d] as WorkingSession), ...patch } });
  const toggle = (d: number, open: boolean) =>
    setDays({
      ...days,
      [d]: open ? { weekday: d, opens_at: "09:00", closes_at: "18:00", break_starts_at: "13:00", break_ends_at: "14:00" } : null,
    });
  const sessions = cleanSessions(Object.values(days).filter((s): s is WorkingSession => !!s));
  const errors = workingHoursErrors(sessions);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!branchId) {
      setError(t("wizNeedBranch"));
      return;
    }
    if (errors.length) {
      setError(errors.map((er) => `${t(`weekday_${er.weekday}`)}: ${t(`hoursErr_${er.code}`)}`).join(" · "));
      return;
    }
    void act(async () => {
      await api.put(`/setup/branches/${branchId}/working-hours`, { sessions });
      await onSaved();
    });
  };
  const time = (d: number, k: keyof WorkingSession, label: string) => (
    <label className="field" style={{ fontWeight: 400 }}>
      <span className="sr-only">{label}</span>
      <input
        type="time"
        aria-label={`${t(`weekday_${d}`)} ${label}`}
        value={hhmm((days[d]?.[k] as string | null) ?? "")}
        onChange={(e) => update(d, { [k]: e.target.value || null })}
      />
    </label>
  );
  return (
    <StepFrame title={t("wizStep_working_hours")} intro={t("wizHoursIntro")} onSubmit={submit} busy={busy}>
      {branches.length > 1 && (
        <label className="field">
          {t("branch")}
          <select value={branchId} onChange={(e) => setBranchId(e.target.value)}>
            {branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t("wizDay")}</th>
              <th>{t("wizOpen")}</th>
              <th>{t("wizOpensAt")}</th>
              <th>{t("wizClosesAt")}</th>
              <th>{t("wizLunchFrom")}</th>
              <th>{t("wizLunchTo")}</th>
            </tr>
          </thead>
          <tbody>
            {[0, 1, 2, 3, 4, 5, 6].map((d) => (
              <tr key={d} className={errors.some((e) => e.weekday === d) ? "field-error" : undefined}>
                <td>{t(`weekday_${d}`)}</td>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`${t(`weekday_${d}`)} ${t("wizOpen")}`}
                    checked={!!days[d]}
                    onChange={(e) => toggle(d, e.target.checked)}
                  />
                </td>
                {days[d] ? (
                  <>
                    <td>{time(d, "opens_at", t("wizOpensAt"))}</td>
                    <td>{time(d, "closes_at", t("wizClosesAt"))}</td>
                    <td>{time(d, "break_starts_at", t("wizLunchFrom"))}</td>
                    <td>{time(d, "break_ends_at", t("wizLunchTo"))}</td>
                  </>
                ) : (
                  <td colSpan={4} className="muted">
                    {t("wizClosed")}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted" style={{ fontSize: "0.85rem" }}>{t("wizHoursNote")}</p>
    </StepFrame>
  );
}

function FeesStep({ onSaved, busy, act, setError }: StepProps) {
  const { t } = useLang();
  const [def, setDef] = useState({ fee: "300", follow: "", days: "7" });
  const [doctors, setDoctors] = useState<Member[]>([]);
  const [own, setOwn] = useState<Record<string, string>>({});
  useEffect(() => {
    Promise.all([api.get<FeesOut>("/setup/fees"), api.get<Member[]>("/members")])
      .then(([fees, ms]) => {
        if (fees.default) {
          setDef({
            fee: feeInput(fees.default.consultation_fee),
            follow: feeInput(fees.default.follow_up_fee),
            days: fees.default.follow_up_valid_days?.toString() ?? "",
          });
        }
        setDoctors(ms.filter((m) => m.role_key === "doctor" || m.role_key === "owner"));
        setOwn(Object.fromEntries(fees.providers.map((p) => [p.provider_user_id ?? "", feeInput(p.consultation_fee)])));
      })
      .catch(() => undefined);
  }, []);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const fee = parseFee(def.fee);
    const follow = parseFee(def.follow);
    const days = def.days.trim() === "" ? null : Number(def.days);
    if (!fee || follow === undefined || (days !== null && !(Number.isInteger(days) && days >= 0 && days <= 365))) {
      setError(t("wizBadFee"));
      return;
    }
    const perDoctor = Object.entries(own).filter(([, v]) => v.trim() !== "");
    if (perDoctor.some(([, v]) => !parseFee(v))) {
      setError(t("wizBadFee"));
      return;
    }
    void act(async () => {
      await api.put("/setup/fees/default", {
        consultation_fee: fee,
        follow_up_fee: follow,
        follow_up_valid_days: days,
      });
      for (const [uid, v] of perDoctor) {
        await api.put(`/setup/fees/providers/${uid}`, { consultation_fee: parseFee(v) });
      }
      await onSaved();
    });
  };
  return (
    <StepFrame title={t("wizStep_fees")} intro={t("wizFeesIntro")} onSubmit={submit} busy={busy}>
      <div className="grid two">
        <label className="field">
          {t("wizConsultFee")} (₹)
          <input type="text" inputMode="decimal" value={def.fee} onChange={(e) => setDef({ ...def, fee: e.target.value })} data-testid="wiz-fee" />
        </label>
        <label className="field">
          {t("wizFollowUpFee")} (₹)
          <input type="text" inputMode="decimal" value={def.follow} onChange={(e) => setDef({ ...def, follow: e.target.value })} placeholder={t("wizOptional")} />
        </label>
        <label className="field">
          {t("wizFollowUpDays")}
          <input type="text" inputMode="numeric" value={def.days} onChange={(e) => setDef({ ...def, days: e.target.value })} />
        </label>
      </div>
      {doctors.length > 0 && (
        <>
          <h3>{t("wizPerDoctor")}</h3>
          <p className="muted" style={{ marginTop: 0 }}>{t("wizPerDoctorHint")}</p>
          <div className="grid two">
            {doctors.map((d) => (
              <label className="field" key={d.user_id}>
                {d.full_name} (₹)
                <input
                  type="text"
                  inputMode="decimal"
                  value={own[d.user_id] ?? ""}
                  placeholder={def.fee}
                  onChange={(e) => setOwn({ ...own, [d.user_id]: e.target.value })}
                />
              </label>
            ))}
          </div>
        </>
      )}
      <p className="muted" style={{ fontSize: "0.85rem" }}>{t("wizFeesNote")}</p>
    </StepFrame>
  );
}

function useSettings() {
  const [doc, setDoc] = useState<OrgSettingsDoc | null>(null);
  useEffect(() => {
    api.get<OrgSettingsOut>("/setup/settings").then((s) => setDoc(s.settings)).catch(() => undefined);
  }, []);
  return [doc, setDoc] as const;
}

function PrescriptionStep({ onSaved, busy, act }: StepProps) {
  const { t } = useLang();
  const [doc, setDoc] = useSettings();
  if (!doc) return <p className="muted">{t("loading")}</p>;
  const p = doc.prescription;
  const set = (patch: Partial<PrescriptionSettings>) => setDoc({ ...doc, prescription: { ...p, ...patch } });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void act(async () => {
      await api.patch("/setup/settings", { prescription: p });
      await onSaved();
    });
  };
  return (
    <StepFrame title={t("wizStep_prescription")} intro={t("wizRxIntro")} onSubmit={submit} busy={busy}>
      <label className="field">
        {t("wizRxHeader")}
        <textarea rows={2} maxLength={500} value={p.header_text} onChange={(e) => set({ header_text: e.target.value })} placeholder={t("wizRxHeaderHint")} />
      </label>
      <label className="field">
        {t("wizRxFooter")}
        <textarea rows={2} maxLength={500} value={p.footer_text} onChange={(e) => set({ footer_text: e.target.value })} placeholder={t("wizRxFooterHint")} />
      </label>
      <div className="grid two">
        <label className="field">
          {t("wizPaperSize")}
          <select value={p.paper_size} onChange={(e) => set({ paper_size: e.target.value as "A4" | "A5" })}>
            <option value="A4">A4</option>
            <option value="A5">A5</option>
          </select>
        </label>
        <label className="field">
          {t("wizRxLanguage")}
          <select value={p.language} onChange={(e) => set({ language: e.target.value as PrescriptionSettings["language"] })}>
            <option value="trilingual">{t("wizTrilingual")}</option>
            {LANGS.map((l) => (
              <option key={l.code} value={l.code}>
                {l.native}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label style={{ display: "block", marginTop: "0.5rem" }}>
        <input type="checkbox" checked={p.show_registration_number} onChange={(e) => set({ show_registration_number: e.target.checked })} />{" "}
        {t("wizShowRegNo")}
      </label>
    </StepFrame>
  );
}

function BillingStep({ onSaved, busy, act, setError }: StepProps) {
  const { t } = useLang();
  const [doc, setDoc] = useSettings();
  if (!doc) return <p className="muted">{t("loading")}</p>;
  const b = doc.billing;
  const set = (patch: Partial<BillingSettings>) => setDoc({ ...doc, billing: { ...b, ...patch } });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!/^[A-Z0-9][A-Z0-9/-]{0,11}$/.test(b.invoice_prefix) || b.default_payment_methods.length === 0) {
      setError(t("wizBadBilling"));
      return;
    }
    void act(async () => {
      await api.patch("/setup/settings", { billing: b });
      await onSaved();
    });
  };
  const toggle = (m: (typeof PAYMENT_METHODS)[number]) =>
    set({
      default_payment_methods: b.default_payment_methods.includes(m)
        ? b.default_payment_methods.filter((x) => x !== m)
        : [...b.default_payment_methods, m],
    });
  return (
    <StepFrame title={t("wizStep_billing")} intro={t("wizBillingIntro")} onSubmit={submit} busy={busy}>
      <div className="grid two">
        <label className="field">
          {t("wizInvoicePrefix")}
          <input type="text" maxLength={12} value={b.invoice_prefix} onChange={(e) => set({ invoice_prefix: e.target.value.toUpperCase() })} />
        </label>
        <label className="field">
          {t("wizReceiptFooter")}
          <input type="text" maxLength={300} value={b.receipt_footer} onChange={(e) => set({ receipt_footer: e.target.value })} placeholder={t("wizReceiptFooterHint")} />
        </label>
      </div>
      <fieldset style={{ border: 0, padding: 0, marginTop: "0.75rem" }}>
        <legend style={{ fontWeight: 600 }}>{t("wizPaymentMethods")}</legend>
        <div className="row" style={{ gap: "1rem", flexWrap: "wrap" }}>
          {PAYMENT_METHODS.map((m) => (
            <label key={m}>
              <input type="checkbox" checked={b.default_payment_methods.includes(m)} onChange={() => toggle(m)} /> {t(`payMethod_${m}`)}
            </label>
          ))}
        </div>
      </fieldset>
      <label style={{ display: "block", marginTop: "0.5rem" }}>
        <input type="checkbox" checked={b.show_gstin} onChange={(e) => set({ show_gstin: e.target.checked })} /> {t("wizShowGstin")}
      </label>
      <p className="muted" style={{ fontSize: "0.85rem" }}>{t("wizBillingNote")}</p>
    </StepFrame>
  );
}

function PrinterStep({ onSaved, busy, act }: StepProps) {
  const { t } = useLang();
  const [kind, setKind] = useState<PrinterKind>("a4");
  const [existing, setExisting] = useState<PrinterProfile[]>([]);
  useEffect(() => {
    api.get<PrinterProfile[]>("/setup/printers").then(setExisting).catch(() => undefined);
  }, []);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void act(async () => {
      const thermal = kind.startsWith("thermal");
      const name = `${t(`printerKind_${kind}`)}`.slice(0, 80);
      if (!existing.some((p) => p.name.toLowerCase() === name.toLowerCase())) {
        await api.post("/setup/printers", {
          name,
          kind,
          default_for: thermal ? ["receipt"] : ["prescription", "receipt", "lab_report"],
          ...(thermal ? { margin_top_mm: 2, margin_right_mm: 2, margin_bottom_mm: 2, margin_left_mm: 2 } : {}),
        });
      }
      await onSaved();
    });
  };
  return (
    <StepFrame title={t("wizStep_printer")} intro={t("wizPrinterIntro")} onSubmit={submit} busy={busy}>
      {existing.length > 0 && (
        <p className="notice">
          {fill(t("wizPrintersExisting"), { list: existing.map((p) => p.name).join(", ") })}
        </p>
      )}
      <div role="radiogroup" className="grid two">
        {PRINTER_KINDS.map((k) => (
          <label key={k} className="card" style={{ padding: "0.75rem", cursor: "pointer" }}>
            <input type="radio" name="kind" checked={kind === k} onChange={() => setKind(k)} />{" "}
            <strong>{t(`printerKind_${k}`)}</strong>
            <span className="muted" style={{ display: "block", fontSize: "0.85rem" }}>
              {t(`printerKindHint_${k}`)}
            </span>
          </label>
        ))}
      </div>
      <p className="muted" style={{ fontSize: "0.85rem" }}>
        {t("wizPrinterNote")} <Link href="/settings/printers">{t("navPrinters")}</Link>
      </p>
    </StepFrame>
  );
}

function ScheduleStep({ onSaved, busy, act }: StepProps) {
  const { t } = useLang();
  const [doc, setDoc] = useSettings();
  if (!doc) return <p className="muted">{t("loading")}</p>;
  const s = doc.schedule;
  const set = (patch: Partial<ScheduleSettings>) => setDoc({ ...doc, schedule: { ...s, ...patch } });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void act(async () => {
      await api.patch("/setup/settings", { schedule: s });
      await onSaved();
    });
  };
  return (
    <StepFrame title={t("wizStep_schedule")} intro={t("wizScheduleIntro")} onSubmit={submit} busy={busy}>
      <div className="grid two">
        <label className="field">
          {t("wizSlotLength")}
          <select value={s.slot_minutes} onChange={(e) => set({ slot_minutes: Number(e.target.value) })}>
            {SLOT_LENGTHS.map((m) => (
              <option key={m} value={m}>
                {fill(t("wizMinutes"), { n: m })}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          {t("wizMaxPerSlot")}
          <input type="number" min={1} max={20} value={s.max_per_slot} onChange={(e) => set({ max_per_slot: Math.max(1, Math.min(20, Number(e.target.value) || 1)) })} />
        </label>
      </div>
      <label style={{ display: "block", marginTop: "0.5rem" }}>
        <input type="checkbox" checked={s.online_booking_enabled} onChange={(e) => set({ online_booking_enabled: e.target.checked })} />{" "}
        {t("wizOnlineBooking")}
      </label>
      <p className="muted" style={{ fontSize: "0.85rem" }}>{t("wizOnlineBookingNote")}</p>
    </StepFrame>
  );
}

function EditionStep({ onSaved, busy }: StepProps) {
  const { t } = useLang();
  const can = useCan();
  const [sub, setSub] = useState<SubscriptionOut | null>(null);
  useEffect(() => {
    if (can("subscription.read")) api.get<SubscriptionOut>("/subscription").then(setSub).catch(() => undefined);
  }, [can]);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void onSaved();
  };
  return (
    <StepFrame title={t("wizStep_edition")} intro={t("wizEditionIntro")} onSubmit={submit} busy={busy} submitLabel={t("wizLooksGood")}>
      {sub ? (
        <div className="card" data-testid="wiz-edition">
          <p style={{ margin: 0 }}>
            {t("currentEdition")}: <strong>{sub.plan.name}</strong> — {t(`subStatus_${sub.effective_status}`)}
          </p>
          {sub.trial_ends_at && (
            <p className="muted" style={{ margin: "0.25rem 0 0" }}>
              {t("wizTrialEnds")}: {new Date(sub.trial_ends_at).toLocaleDateString()}
            </p>
          )}
        </div>
      ) : (
        <p className="muted">{t("loading")}</p>
      )}
      <p>
        <Link href="/settings/subscription">{t("viewSubscription")}</Link>
      </p>
      <p className="muted" style={{ fontSize: "0.85rem" }}>{t("wizEditionNote")}</p>
    </StepFrame>
  );
}

const STEP_COMPONENTS: Record<WizardStepKey, (p: StepProps) => ReactNode> = {
  identity: IdentityStep,
  branch: BranchStep,
  staff: StaffStep,
  language: LanguageStep,
  working_hours: WorkingHoursStep,
  fees: FeesStep,
  prescription: PrescriptionStep,
  billing: BillingStep,
  printer: PrinterStep,
  schedule: ScheduleStep,
  edition: EditionStep,
};

// --- wizard shell -------------------------------------------------------------------------
function WizardBody() {
  const { t } = useLang();
  const router = useRouter();
  const { busy, error, notice, setError, setNotice, act } = useAction();
  const [state, setState] = useState<WizardState | null>(null);
  const [step, setStep] = useState<WizardStepKey>("identity");

  useEffect(() => {
    api
      .get<WizardState>("/setup/wizard")
      .then((s) => {
        setState(s);
        setStep(resumeStep(s));
      })
      .catch((err) => setError(serverMessage(err, t("loadFailed"))));
  }, [setError, t]);

  const go = async (key: WizardStepKey) => {
    setError(null);
    setNotice(null);
    setStep(key);
    try {
      setState(await api.patch<WizardState>("/setup/wizard", { current_step: key }));
    } catch {
      /* navigation still works offline-ish; progress is saved on the next mark */
    }
    window.scrollTo?.({ top: 0 });
  };

  const mark = async (status: "done" | "skipped") => {
    const s = await api.post<WizardState>(`/setup/wizard/steps/${step}`, { status });
    setState(s);
    const next = neighbourStep(step, 1);
    if (next) {
      setStep(next);
      setNotice(status === "done" ? t("saved") : t("wizSkippedNotice"));
    } else {
      setNotice(t("wizAllStepsSeen"));
    }
    window.scrollTo?.({ top: 0 });
  };

  const finish = () =>
    void act(async () => {
      await api.patch("/setup/wizard", { finished: true });
      router.push("/dashboard");
    });

  if (!state) {
    return (
      <main className="page">
        <h1 style={{ marginTop: 0 }}>{t("wizTitle")}</h1>
        <Messages error={error} notice={notice} />
        {!error && <p className="muted">{t("loading")}</p>}
      </main>
    );
  }

  const Current = STEP_COMPONENTS[step];
  const statusOf = (k: WizardStepKey) => state.steps.find((s) => s.key === k);
  const index = WIZARD_STEPS.indexOf(step);
  return (
    <main className="page" data-testid="setup-wizard">
      <h1 style={{ marginTop: 0 }}>{t("wizTitle")}</h1>
      <p className="muted" style={{ marginTop: 0 }}>{t("wizIntro")}</p>
      <div
        className="meter ok"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={state.progress_percent}
        aria-label={t("wizProgress")}
        style={{ marginBottom: "1rem" }}
      >
        <span style={{ fontWeight: 600 }}>
          {fill(t("wizStepOf"), { n: index + 1, total: WIZARD_STEPS.length })}
        </span>
        <div className="bar">
          <div className="fill" style={{ width: `${state.progress_percent}%` }} data-testid="wizard-progress" />
        </div>
        <span className="figure">{state.progress_percent}%</span>
      </div>

      <nav aria-label={t("wizProgress")} style={{ marginBottom: "1rem" }}>
        <ol className="steps" style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", padding: 0, listStyle: "none" }}>
          {WIZARD_STEPS.map((k) => {
            const s = statusOf(k);
            const sym = s?.status === "done" ? "✓" : s?.status === "skipped" ? "–" : "";
            return (
              <li key={k}>
                <button
                  type="button"
                  className={k === step ? "primary" : "chip"}
                  aria-current={k === step ? "step" : undefined}
                  onClick={() => void go(k)}
                  data-testid={`wizard-nav-${k}`}
                >
                  {sym && <span aria-hidden="true">{sym} </span>}
                  {t(`wizStep_${k}`)}
                  <span className="sr-only">
                    {" "}
                    ({s?.status === "done" ? t("stepDone") : s?.status === "skipped" ? t("wizSkipped") : t("stepTodo")})
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      </nav>

      <Messages error={error} notice={notice} />
      <section className="card" data-testid={`wizard-step-${step}`}>
        <Current onSaved={() => mark("done")} busy={busy} act={act} setError={setError} />
        <div className="row" style={{ gap: "0.5rem", marginTop: "0.75rem", flexWrap: "wrap" }}>
          {neighbourStep(step, -1) && (
            <button type="button" className="secondary" onClick={() => void go(neighbourStep(step, -1) as WizardStepKey)} disabled={busy}>
              {t("wizBack")}
            </button>
          )}
          <button type="button" className="ghost" onClick={() => void act(() => mark("skipped"))} disabled={busy} data-testid="wizard-skip">
            {t("wizSkip")}
          </button>
        </div>
      </section>

      <section className="card" style={{ marginTop: "1rem" }}>
        <p style={{ marginTop: 0 }}>{t("wizFinishHint")}</p>
        <button type="button" className="primary" onClick={finish} disabled={busy} data-testid="wizard-finish">
          {t("wizFinish")}
        </button>
      </section>
    </main>
  );
}

export default function SetupPage() {
  return (
    <AppShell active="setup">
      <WizardBody />
    </AppShell>
  );
}
