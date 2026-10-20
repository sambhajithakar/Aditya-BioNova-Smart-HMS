"use client";

/**
 * Printer test page: corner alignment marks, a 50 mm ruler and a sample
 * receipt with SYNTHETIC data, on A4 / A5 / 80 mm thermal roll (the same
 * print CSS as /print/rx/[id], lib/print-paper.ts). No API calls, no patient
 * data. Physical printers have not been tested in development — this page
 * exists so each clinic can check its own printer once.
 */
import { Suspense } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useLang } from "@/lib/lang";
import { PAPERS, Paper, pageCss, parsePaper } from "@/lib/print-paper";

const SAMPLE = {
  clinic: "Sample Clinic (synthetic)",
  branch: "Test branch",
  invoice: "TEST-0001",
  patient: "Test Patient",
  uhid: "P0000000",
  lines: [
    { d: "OPD consultation", q: 1, r: 300 },
    { d: "Dressing", q: 1, r: 150 },
    { d: "Paracetamol 500 mg ×10", q: 1, r: 25.5 },
  ],
};

export default function PrinterTestPage() {
  return (
    <Suspense fallback={null}>
      <PrinterTest />
    </Suspense>
  );
}

function PrinterTest() {
  const { t } = useLang();
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const paper = parsePaper(search.get("paper"), true);
  const total = SAMPLE.lines.reduce((a, l) => a + l.q * l.r, 0);
  const label: Record<Paper, string> = { a4: t("devPaperA4"), a5: t("devPaperA5"), "80mm": t("devPaper80") };

  return (
    <main className={`print-sheet paper-${paper} printer-test`} data-testid="printer-test" data-paper={paper}>
      <span className="mark tl" aria-hidden="true" />
      <span className="mark tr" aria-hidden="true" />
      <span className="mark bl" aria-hidden="true" />
      <span className="mark br" aria-hidden="true" />

      <h1>{t("devPrintTestTitle")}</h1>
      <p className="no-print">{t("devPrintTestIntro")}</p>

      <div className="no-print paper-picker" role="group" aria-label={t("devPaper")}>
        {PAPERS.map((p) => (
          <button
            key={p}
            type="button"
            aria-pressed={p === paper}
            data-testid={`paper-${p}`}
            onClick={() => router.replace(`${pathname}?paper=${p}`)}
          >
            {label[p]}
          </button>
        ))}
        <button type="button" className="go" onClick={() => window.print()}>
          {t("devPrint")}
        </button>
      </div>

      <p className="meta">
        {t("devPaper")}: <strong>{label[paper]}</strong>
      </p>
      <div className="ruler" aria-label={t("devRuler")} data-testid="ruler">
        {Array.from({ length: 6 }, (_, i) => (
          <span key={i} style={{ left: `${i * 10}mm` }}>
            {i * 10}
          </span>
        ))}
      </div>
      <p className="meta">{t("devRuler")}</p>
      <p className="glyphs">
        ABCDEFGHIJKLM 0123456789 ₹ — मराठी: औषधपत्र पावती — हिंदी: पर्चा रसीद
      </p>

      <section className="sample" aria-label={t("devSampleReceipt")}>
        <header className="print-head">
          <div>
            <h2>{SAMPLE.clinic}</h2>
            <p className="tri">{SAMPLE.branch} — RECEIPT / पावती / रसीद</p>
          </div>
          <div className="right">
            <p>
              <strong>{SAMPLE.invoice}</strong>
            </p>
          </div>
        </header>
        <p>
          Patient: <strong>{SAMPLE.patient}</strong> · UHID {SAMPLE.uhid}
        </p>
        <table className="print-table">
          <thead>
            <tr>
              <th>Description</th>
              <th>Qty</th>
              <th className="num">Amount</th>
            </tr>
          </thead>
          <tbody>
            {SAMPLE.lines.map((l) => (
              <tr key={l.d}>
                <td>{l.d}</td>
                <td>{l.q}</td>
                <td className="num">{(l.q * l.r).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="total">
          Total / एकूण / कुल: <strong>₹ {total.toFixed(2)}</strong>
        </p>
        <p className="tri">{t("devSampleReceipt")}</p>
      </section>

      <style>{TEST_CSS + pageCss(paper)}</style>
    </main>
  );
}

const TEST_CSS = `
  .print-sheet { font-family: Georgia, "Noto Serif", serif; color: #101828; position: relative;
    max-width: 800px; margin: 0 auto; padding: 1.5rem; background: #fff; }
  .printer-test h1 { font-size: 1.3rem; margin: 0.5rem 0; }
  .printer-test h2 { font-size: 1.1rem; margin: 0; }
  .printer-test .mark { position: absolute; width: 8mm; height: 8mm; border: 0 solid #000; }
  .printer-test .tl { top: 0; left: 0; border-top-width: 0.6mm; border-left-width: 0.6mm; }
  .printer-test .tr { top: 0; right: 0; border-top-width: 0.6mm; border-right-width: 0.6mm; }
  .printer-test .bl { bottom: 0; left: 0; border-bottom-width: 0.6mm; border-left-width: 0.6mm; }
  .printer-test .br { bottom: 0; right: 0; border-bottom-width: 0.6mm; border-right-width: 0.6mm; }
  .printer-test .ruler { position: relative; width: 50mm; height: 6mm; margin-top: 4mm;
    border-bottom: 0.4mm solid #000;
    background: repeating-linear-gradient(to right, #000 0 0.3mm, transparent 0.3mm 5mm) bottom / 100% 2mm no-repeat; }
  .printer-test .ruler span { position: absolute; bottom: 2.5mm; font-size: 8px; transform: translateX(-50%); }
  .printer-test .meta { font-size: 0.85rem; margin: 0.2rem 0; }
  .printer-test .glyphs { font-size: 0.9rem; }
  .printer-test .sample { margin-top: 1rem; border-top: 1px dashed #486581; padding-top: 0.5rem; }
  .printer-test .right { text-align: right; }
  .printer-test .num { text-align: right; }
  .printer-test .total { text-align: right; }
  .print-head { display: flex; justify-content: space-between; border-bottom: 3px double #1d3557;
    padding-bottom: 0.4rem; margin-bottom: 0.4rem; }
  .print-head p { margin: 0.1rem 0; }
  .tri { color: #486581; font-size: 0.85em; }
  .print-table { width: 100%; border-collapse: collapse; }
  .print-table th, .print-table td { border: 1px solid #bcccdc; padding: 0.3rem 0.4rem; text-align: left; }
  .paper-picker { display: flex; gap: 0.4rem; flex-wrap: wrap; margin: 0.75rem 0; }
  .paper-picker button { min-height: 44px; padding: 0.3rem 0.9rem; border: 1px solid #486581;
    border-radius: 8px; background: #fff; color: #101828; cursor: pointer; font: inherit; }
  .paper-picker button[aria-pressed="true"] { background: #1d3557; color: #fff; }
  .paper-picker button.go { background: #0f766e; color: #fff; border-color: #0f766e; font-weight: 700; }
  @media print {
    .no-print { display: none !important; }
    .print-sheet { max-width: none; padding: 0; }
  }
`;
