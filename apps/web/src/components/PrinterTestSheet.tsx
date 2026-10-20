"use client";

/**
 * Printer test page: alignment marks in the four corners, millimetre rulers,
 * a sample (synthetic) receipt / prescription and Devanagari text, so a
 * clinic can check paper size, margins, scaling and font rendering from the
 * browser print preview before printing real documents.
 */
import { PageGeometry, PAPER, fill } from "@/lib/setup";
import { useLang } from "@/lib/lang";

function Ruler({ lengthMm, vertical = false }: { lengthMm: number; vertical?: boolean }) {
  const ticks = [];
  for (let i = 0; i <= lengthMm; i += 1) {
    const h = i % 10 === 0 ? 4 : i % 5 === 0 ? 2.5 : 1.5;
    ticks.push(
      vertical ? (
        <line key={i} x1={0} y1={i} x2={h} y2={i} stroke="#000" strokeWidth={0.15} />
      ) : (
        <line key={i} x1={i} y1={0} x2={i} y2={h} stroke="#000" strokeWidth={0.15} />
      ),
    );
    if (i % 10 === 0 && i > 0) {
      ticks.push(
        <text
          key={`t${i}`}
          x={vertical ? 4.5 : i}
          y={vertical ? i + 1 : 7}
          fontSize={2.6}
          textAnchor={vertical ? "start" : "middle"}
        >
          {i / 10}
        </text>,
      );
    }
  }
  const w = vertical ? 10 : lengthMm;
  const hgt = vertical ? lengthMm : 9;
  return (
    <svg
      width={`${w}mm`}
      height={`${hgt}mm`}
      viewBox={`0 0 ${w} ${hgt}`}
      aria-hidden="true"
      style={{ display: "block", overflow: "visible" }}
    >
      {ticks}
    </svg>
  );
}

export function PrinterTestSheet({ geometry, profileName }: { geometry: PageGeometry; profileName: string }) {
  const { t } = useLang();
  const thermal = geometry.kind.startsWith("thermal");
  const rulerMm = Math.floor(geometry.contentWidthMm);
  const paper = PAPER[geometry.kind];
  return (
    <div className="test-sheet" data-testid="printer-test-sheet">
      <span className="mark tl" aria-hidden="true" />
      <span className="mark tr" aria-hidden="true" />
      {!thermal && <span className="mark bl" aria-hidden="true" />}
      {!thermal && <span className="mark br" aria-hidden="true" />}

      <h2 style={{ margin: "0 0 0.25rem" }}>{t("printerTestTitle")}</h2>
      <p style={{ margin: 0 }}>
        {profileName} · {t(`printerKind_${geometry.kind}`)} · {paper.widthMm}
        {paper.heightMm ? ` × ${paper.heightMm}` : ""} mm · {t("printerMargins")}{" "}
        {geometry.margins.join(" / ")} mm · {t("printerFontScale")} {geometry.fontScale}×
      </p>

      <h3>{t("printerRulerHorizontal")}</h3>
      <Ruler lengthMm={rulerMm} />
      <p className="hint">{fill(t("printerRulerHint"), { mm: rulerMm })}</p>

      {!thermal && (
        <div style={{ display: "flex", gap: "4mm", alignItems: "flex-start" }}>
          <Ruler lengthMm={50} vertical />
          <p className="hint">{t("printerRulerVerticalHint")}</p>
        </div>
      )}

      <h3>{t("printerSampleReceipt")}</h3>
      <table className="sample">
        <tbody>
          <tr>
            <td>{t("printerSampleConsult")}</td>
            <td style={{ textAlign: "right" }}>₹ 300.00</td>
          </tr>
          <tr>
            <td>{t("printerSampleDressing")}</td>
            <td style={{ textAlign: "right" }}>₹ 150.00</td>
          </tr>
          <tr>
            <th>{t("printerSampleTotal")}</th>
            <th style={{ textAlign: "right" }}>₹ 450.00</th>
          </tr>
        </tbody>
      </table>

      <h3>{t("printerSampleRx")}</h3>
      <ol className="sample-rx">
        <li>Tab. Paracetamol 500 mg — 1-0-1 × 3 {t("printerSampleDays")}</li>
        <li>Syp. Synthetic Tonic 10 ml — 0-0-1 × 5 {t("printerSampleDays")}</li>
      </ol>

      <h3>{t("printerDevanagari")}</h3>
      <p lang="mr" className="deva">मराठी: रुग्णाचे नाव, औषधे, सल्ला — क्ष त्र ज्ञ श्र ॐ ₹ १२३४५६७८९०</p>
      <p lang="hi" className="deva">हिंदी: रोगी का नाम, दवाइयाँ, सलाह — क्षत्रिय, ज्ञान, श्रद्धा, द्वार, ह्रस्व</p>
      <p className="hint">{t("printerDevanagariHint")}</p>
      <p className="hint">{t("printerSyntheticNote")}</p>
      <style>{TEST_CSS}</style>
    </div>
  );
}

const TEST_CSS = `
  .test-sheet { position: relative; padding: 6mm 4mm; color: #000; background: #fff; }
  .test-sheet h3 { margin: 0.6rem 0 0.2rem; font-size: 1em; }
  .test-sheet .hint { color: #333; font-size: 0.85em; margin: 0.2rem 0; }
  .test-sheet .mark { position: absolute; width: 5mm; height: 5mm; border: 0 solid #000; }
  .test-sheet .mark.tl { top: 0; left: 0; border-top-width: 0.4mm; border-left-width: 0.4mm; }
  .test-sheet .mark.tr { top: 0; right: 0; border-top-width: 0.4mm; border-right-width: 0.4mm; }
  .test-sheet .mark.bl { bottom: 0; left: 0; border-bottom-width: 0.4mm; border-left-width: 0.4mm; }
  .test-sheet .mark.br { bottom: 0; right: 0; border-bottom-width: 0.4mm; border-right-width: 0.4mm; }
  .test-sheet table.sample { width: 100%; border-collapse: collapse; }
  .test-sheet table.sample td, .test-sheet table.sample th { border-bottom: 1px dashed #000;
    padding: 0.15rem 0; text-align: left; }
  .test-sheet .deva { font-family: "Noto Sans Devanagari", "Mangal", "Nirmala UI", sans-serif;
    font-size: 1.1em; }
  .test-sheet .sample-rx { padding-left: 1.2em; margin: 0.2rem 0; }
`;
