"use client";

/**
 * Server-side patient search (fixes D9: pickers limited to the first 100
 * patients). Debounced type-ahead against GET /patients?q=…; stale responses
 * are discarded. Calls `onChange(id, patient)` when a result is picked.
 */
import { useEffect, useRef, useState } from "react";
import { PageOf, Patient, api } from "@/lib/api";
import { useLang } from "@/lib/lang";

export function patientLabel(p: Pick<Patient, "uhid" | "full_name">): string {
  return `${p.uhid} — ${p.full_name}`;
}

export function PatientPicker({
  id,
  value,
  onChange,
  disabled,
  showAllergies = false,
}: {
  id: string;
  value: string;
  onChange: (id: string, patient: Patient | null) => void;
  disabled?: boolean;
  showAllergies?: boolean;
}) {
  const { t } = useLang();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Patient[]>([]);
  const [picked, setPicked] = useState<Patient | null>(null);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);

  useEffect(() => {
    if (!value) setPicked(null);
  }, [value]);

  useEffect(() => {
    const mine = ++seq.current;
    const handle = setTimeout(() => {
      setLoading(true);
      api
        .get<PageOf<Patient>>(`/patients?limit=20${q.trim() ? `&q=${encodeURIComponent(q.trim())}` : ""}`)
        .then((page) => {
          if (mine === seq.current) setResults(page.items);
        })
        .catch(() => {
          if (mine === seq.current) setResults([]);
        })
        .finally(() => {
          if (mine === seq.current) setLoading(false);
        });
    }, 250);
    return () => clearTimeout(handle);
  }, [q]);

  const options = picked && !results.some((r) => r.id === picked.id) ? [picked, ...results] : results;

  return (
    <div className="field patient-picker">
      <label htmlFor={`${id}-q`}>{t("patients")}</label>
      <input
        id={`${id}-q`}
        type="search"
        value={q}
        placeholder={t("searchPatient")}
        onChange={(e) => setQ(e.target.value)}
        disabled={disabled}
        aria-controls={id}
        autoComplete="off"
      />
      <select
        id={id}
        aria-label={t("patients")}
        value={value}
        disabled={disabled}
        onChange={(e) => {
          const p = options.find((x) => x.id === e.target.value) ?? null;
          setPicked(p);
          onChange(e.target.value, p);
        }}
      >
        <option value="">{loading ? t("loading") : `— ${t("selectPatient")} (${options.length}) —`}</option>
        {options.map((p) => (
          <option key={p.id} value={p.id}>
            {patientLabel(p)}
            {showAllergies && p.allergies ? ` ⚠ ${p.allergies}` : ""}
          </option>
        ))}
      </select>
    </div>
  );
}
