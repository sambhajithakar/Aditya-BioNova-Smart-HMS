"use client";

/**
 * Smart Printer Setup: the clinic's printer profiles (paper kind, margins,
 * font scale, which documents use it by default) with a live test-page
 * preview. Printing goes through the browser's own print dialog — this page
 * cannot see physical printers; use the test page to check alignment.
 */
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { PrinterTestSheet } from "@/components/PrinterTestSheet";
import { Messages, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { useCan } from "@/lib/me";
import {
  PAPER,
  PRINTER_KINDS,
  PRINT_DOCUMENTS,
  PrintDocument,
  PrinterKind,
  PrinterProfile,
  pageGeometry,
} from "@/lib/setup";

type Form = {
  name: string;
  kind: PrinterKind;
  default_for: PrintDocument[];
  margin_top_mm: string;
  margin_right_mm: string;
  margin_bottom_mm: string;
  margin_left_mm: string;
  font_scale: string;
  notes: string;
};

const EMPTY: Form = {
  name: "",
  kind: "a4",
  default_for: [],
  margin_top_mm: "10",
  margin_right_mm: "10",
  margin_bottom_mm: "10",
  margin_left_mm: "10",
  font_scale: "1",
  notes: "",
};
const MARGINS = ["margin_top_mm", "margin_right_mm", "margin_bottom_mm", "margin_left_mm"] as const;

function toForm(p: PrinterProfile): Form {
  return {
    name: p.name,
    kind: p.kind,
    default_for: p.default_for,
    margin_top_mm: String(Number(p.margin_top_mm)),
    margin_right_mm: String(Number(p.margin_right_mm)),
    margin_bottom_mm: String(Number(p.margin_bottom_mm)),
    margin_left_mm: String(Number(p.margin_left_mm)),
    font_scale: String(Number(p.font_scale)),
    notes: p.notes,
  };
}

function formValid(f: Form): boolean {
  const okMargin = MARGINS.every((k) => /^\d{1,2}(\.\d)?$/.test(f[k]) && Number(f[k]) <= 50);
  const fs = Number(f.font_scale);
  return f.name.trim().length > 0 && okMargin && Number.isFinite(fs) && fs >= 0.5 && fs <= 2;
}

function PrintersBody() {
  const { t } = useLang();
  const can = useCan();
  const manage = can("setup.manage");
  const { busy, error, notice, setError, setNotice, act } = useAction();
  const [profiles, setProfiles] = useState<PrinterProfile[]>([]);
  const [editing, setEditing] = useState<string | null>(null); // id or "new"
  const [form, setForm] = useState<Form>(EMPTY);

  const load = useCallback(async () => {
    try {
      setProfiles(await api.get<PrinterProfile[]>("/setup/printers"));
    } catch {
      setError(t("loadFailed"));
    }
  }, [setError, t]);
  useEffect(() => {
    void load();
  }, [load]);

  const previewProfile: PrinterProfile = {
    id: editing ?? "preview",
    created_at: "",
    updated_at: "",
    ...form,
  };
  const geometry = pageGeometry(previewProfile);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!formValid(form)) {
      setError(t("printerInvalid"));
      return;
    }
    const body = {
      ...form,
      name: form.name.trim(),
      margin_top_mm: Number(form.margin_top_mm),
      margin_right_mm: Number(form.margin_right_mm),
      margin_bottom_mm: Number(form.margin_bottom_mm),
      margin_left_mm: Number(form.margin_left_mm),
      font_scale: Number(Number(form.font_scale).toFixed(2)),
    };
    void act(async () => {
      if (editing && editing !== "new") await api.patch(`/setup/printers/${editing}`, body);
      else await api.post("/setup/printers", body);
      setNotice(t("saved"));
      setEditing(null);
      setForm(EMPTY);
      await load();
    });
  };

  const remove = (p: PrinterProfile) =>
    void act(async () => {
      if (!window.confirm(t("printerDeleteConfirm"))) return;
      await api.del(`/setup/printers/${p.id}`);
      await load();
    });

  const toggleDoc = (d: PrintDocument) =>
    setForm({
      ...form,
      default_for: form.default_for.includes(d) ? form.default_for.filter((x) => x !== d) : [...form.default_for, d],
    });

  return (
    <main className="page">
      <h1 style={{ marginTop: 0 }}>{t("printersTitle")}</h1>
      <p className="muted" style={{ marginTop: 0 }}>{t("printersIntro")}</p>
      <p className="notice" data-testid="printers-honesty">{t("printersBrowserOnly")}</p>
      <Messages error={error} notice={notice} />

      <section className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t("printerName")}</th>
                <th>{t("printerKind")}</th>
                <th>{t("printerDefaultFor")}</th>
                <th>{t("printerMargins")}</th>
                <th>{t("actions")}</th>
              </tr>
            </thead>
            <tbody>
              {profiles.map((p) => (
                <tr key={p.id} data-testid="printer-row">
                  <td>{p.name}</td>
                  <td>{t(`printerKind_${p.kind}`)}</td>
                  <td>{p.default_for.map((d) => t(`printDoc_${d}`)).join(", ") || "—"}</td>
                  <td>
                    {MARGINS.map((k) => Number(p[k])).join(" / ")} mm · {Number(p.font_scale)}×
                  </td>
                  <td>
                    <Link href={`/print/test?profile=${p.id}`} target="_blank" rel="noopener">
                      {t("printerTestPage")}
                    </Link>{" "}
                    {manage && (
                      <>
                        <button
                          type="button"
                          className="chip"
                          onClick={() => {
                            setEditing(p.id);
                            setForm(toForm(p));
                          }}
                        >
                          {t("printerEdit")}
                        </button>
                        <button type="button" className="chip" onClick={() => remove(p)} disabled={busy}>
                          {t("printerDelete")}
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {profiles.length === 0 && (
                <tr>
                  <td colSpan={5} className="muted">
                    {t("printerNone")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {manage && editing === null && (
          <button
            type="button"
            className="primary"
            onClick={() => {
              setEditing("new");
              setForm(EMPTY);
            }}
            data-testid="printer-add"
          >
            {t("printerAdd")}
          </button>
        )}
      </section>

      {manage && editing !== null && (
        <section className="card" style={{ marginTop: "1rem" }}>
          <form onSubmit={submit} noValidate>
            <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0 }}>
              <div className="grid two">
                <label className="field">
                  {t("printerName")}
                  <input type="text" maxLength={80} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="printer-name" />
                </label>
                <label className="field">
                  {t("printerKind")}
                  <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as PrinterKind })} data-testid="printer-kind">
                    {PRINTER_KINDS.map((k) => (
                      <option key={k} value={k}>
                        {t(`printerKind_${k}`)}
                      </option>
                    ))}
                  </select>
                </label>
                {MARGINS.map((k) => (
                  <label className="field" key={k}>
                    {t(`printer_${k}`)} (mm)
                    <input type="text" inputMode="decimal" value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
                  </label>
                ))}
                <label className="field">
                  {t("printerFontScale")}
                  <input type="number" min={0.5} max={2} step={0.05} value={form.font_scale} onChange={(e) => setForm({ ...form, font_scale: e.target.value })} />
                </label>
                <label className="field">
                  {t("printerNotes")}
                  <input type="text" maxLength={300} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
                </label>
              </div>
              <fieldset style={{ border: 0, padding: 0, marginTop: "0.75rem" }}>
                <legend style={{ fontWeight: 600 }}>{t("printerDefaultFor")}</legend>
                <div className="row" style={{ gap: "1rem", flexWrap: "wrap" }}>
                  {PRINT_DOCUMENTS.map((d) => (
                    <label key={d}>
                      <input type="checkbox" checked={form.default_for.includes(d)} onChange={() => toggleDoc(d)} /> {t(`printDoc_${d}`)}
                    </label>
                  ))}
                </div>
                <p className="muted" style={{ fontSize: "0.85rem" }}>{t("printerDefaultHint")}</p>
              </fieldset>
              <div className="row" style={{ gap: "0.5rem", marginTop: "0.75rem" }}>
                <button className="primary" type="submit" data-testid="printer-save">
                  {t("save")}
                </button>
                <button
                  className="secondary"
                  type="button"
                  onClick={() => {
                    setEditing(null);
                    setForm(EMPTY);
                  }}
                >
                  {t("cancel")}
                </button>
              </div>
            </fieldset>
          </form>
        </section>
      )}

      <section className="card" style={{ marginTop: "1rem" }}>
        <h2 style={{ marginTop: 0 }}>{t("printerPreview")}</h2>
        <p className="muted" style={{ marginTop: 0 }}>{t("printerPreviewHint")}</p>
        <div style={{ overflowX: "auto", background: "#e4e7ec", padding: "0.75rem", borderRadius: 6 }}>
          <div
            data-testid="printer-preview"
            style={{
              width: `${PAPER[geometry.kind].widthMm}mm`,
              minHeight: PAPER[geometry.kind].heightMm ? `${Math.min(PAPER[geometry.kind].heightMm ?? 0, 160)}mm` : undefined,
              padding: `${geometry.margins[0]}mm ${geometry.margins[1]}mm ${geometry.margins[2]}mm ${geometry.margins[3]}mm`,
              background: "#fff",
              boxShadow: "0 1px 4px rgba(0,0,0,0.25)",
              fontSize: `${geometry.fontScale * 100}%`,
              boxSizing: "border-box",
            }}
          >
            <PrinterTestSheet geometry={geometry} profileName={form.name || t("printerUnsaved")} />
          </div>
        </div>
      </section>
    </main>
  );
}

export default function PrintersPage() {
  return (
    <AppShell active="printers">
      <PrintersBody />
    </AppShell>
  );
}
