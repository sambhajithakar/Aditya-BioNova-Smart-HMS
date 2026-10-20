/**
 * Paper sizes for the browser print pipeline (/print/rx/[id] and
 * /print/test). Pure CSS: `@page { size }` + a sheet width per paper.
 *
 * - A4 (default) and A5: prescriptions and receipts.
 * - 80 mm thermal roll: RECEIPTS ONLY (a prescription needs the full page
 *   layout, signature block and amendments), `@page { size: 80mm auto }` so
 *   the roll is cut after the content. 72 mm printable width is the common
 *   80 mm-printer head width; physical printers were NOT tested here.
 */
export type Paper = "a4" | "a5" | "80mm";

export const PAPERS: Paper[] = ["a4", "a5", "80mm"];

export function parsePaper(param: string | null | undefined, isReceipt: boolean): Paper {
  if (param === "a5") return "a5";
  if (param === "80mm" && isReceipt) return "80mm";
  return "a4";
}

export function papersFor(isReceipt: boolean): Paper[] {
  return isReceipt ? PAPERS : ["a4", "a5"];
}

/** Print CSS for a paper (appended after the base print sheet CSS). */
export function pageCss(paper: Paper): string {
  if (paper === "80mm") {
    return `
  .print-sheet.paper-80mm { max-width: 72mm; padding: 2mm; font-size: 11px; line-height: 1.3; }
  .paper-80mm .print-head { display: block; text-align: center; border-bottom: 1px dashed #101828; }
  .paper-80mm .print-head > div { text-align: center !important; }
  .paper-80mm .print-head h1 { font-size: 14px; letter-spacing: 0; }
  .paper-80mm p { margin: 0.1rem 0; }
  .paper-80mm .print-table th, .paper-80mm .print-table td { border: 0; border-bottom: 1px dotted #888;
    padding: 1px 2px; font-size: 11px; }
  .paper-80mm .print-table th { background: none; }
  .paper-80mm .tri { font-size: 10px; }
  .paper-80mm .print-foot { margin-top: 4mm; justify-content: center; }
  @media print {
    @page { size: 80mm auto; margin: 3mm 4mm; }
    .print-sheet.paper-80mm { max-width: none; width: 72mm; padding: 0; }
  }`;
  }
  if (paper === "a5") {
    return `
  .print-sheet.paper-a5 { max-width: 560px; font-size: 13px; }
  .paper-a5 .print-head h1 { font-size: 1.15rem; }
  .paper-a5 .print-table th, .paper-a5 .print-table td { padding: 0.25rem 0.35rem; font-size: 12px; }
  .paper-a5 .print-foot { margin-top: 1.5rem; }
  @media print { @page { size: A5; margin: 10mm; } }`;
  }
  return `
  @media print { @page { size: A4; margin: 14mm; } }`;
}

export const PAPER_LABEL: Record<Paper, { en: string; mr: string; hi: string }> = {
  a4: { en: "A4", mr: "A4", hi: "A4" },
  a5: { en: "A5", mr: "A5", hi: "A5" },
  "80mm": { en: "80 mm roll", mr: "80 मिमी रोल", hi: "80 मिमी रोल" },
};
