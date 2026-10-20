"use client";

/**
 * Printable A4/A5 prescription & receipt (M3).
 *
 * Trilingual by design: labels render in English, Marathi and Hindi
 * together (Indian clinical paperwork convention), while the clinician's
 * own text stays in the language it was written. Uses the browser's
 * print pipeline (Save as PDF) — no server-side PDF dependency.
 * `?type=receipt` switches the layout to the billing receipt.
 */
import { Suspense, useEffect, useState } from "react";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  ApiError,
  Branch,
  Drug,
  EncounterDetail,
  Me,
  Member,
  Patient,
  Prescriber,
  PrescriptionDetail,
  Receipt,
  api,
} from "@/lib/api";
import { onAuthFailure } from "@/lib/session";
import { itemDrugName } from "@/lib/print";
import { PAPER_LABEL, Paper, pageCss, papersFor, parsePaper } from "@/lib/print-paper";

type Label = { en: string; mr: string; hi: string };

const L = {
  prescription: { en: "PRESCRIPTION", mr: "औषधपत्र", hi: "पर्चा" },
  receipt: { en: "RECEIPT", mr: "पावती", hi: "रसीद" },
  patient: { en: "Patient", mr: "रुग्ण", hi: "रोगी" },
  uhid: { en: "UHID", mr: "यूएचआयडी", hi: "यूएचआईडी" },
  date: { en: "Date", mr: "दिनांक", hi: "तिथि" },
  diagnosis: { en: "Diagnosis", mr: "निदान", hi: "निदान" },
  advice: { en: "Advice", mr: "सल्ला", hi: "सलाह" },
  followUp: { en: "Follow-up", mr: "पुनरावृत्ती", hi: "फ़ॉलो-अप" },
  medicines: { en: "Medicines", mr: "औषधे", hi: "दवाइयाँ" },
  dose: { en: "Dose", mr: "प्रमाण", hi: "खुराक" },
  frequency: { en: "Frequency", mr: "वारंवारता", hi: "आवृत्ति" },
  days: { en: "Days", mr: "दिवस", hi: "दिन" },
  signature: { en: "Signature & Seal", mr: "सही व मुद्रा", hi: "हस्ताक्षर व मुहर" },
  items: { en: "Description", mr: "वर्णन", hi: "विवरण" },
  qty: { en: "Qty", mr: "नग", hi: "मात्रा" },
  rate: { en: "Rate", mr: "दर", hi: "दर" },
  amount: { en: "Amount", mr: "रक्कम", hi: "राशि" },
  total: { en: "Total", mr: "एकूण", hi: "कुल" },
  paid: { en: "Paid", mr: "भरले", hi: "भुगतान" },
  balance: { en: "Balance due", mr: "थकबाकी", hi: "शेष" },
  payment: { en: "Payment", mr: "पेमेंट", hi: "भुगतान" },
  allergies: { en: "Allergies", mr: "ऍलर्जी", hi: "एलर्जी" },
  version: { en: "Version", mr: "आवृत्ती", hi: "संस्करण" },
  route: { en: "Route", mr: "मार्ग", hi: "मार्ग" },
  qtyDispense: { en: "Dispense", mr: "देय नग", hi: "देय मात्रा" },
  prescriber: { en: "Prescriber", mr: "डॉक्टर", hi: "चिकित्सक" },
  regNo: { en: "Reg. No.", mr: "नोंदणी क्र.", hi: "पंजीकरण सं." },
  branch: { en: "Branch", mr: "शाखा", hi: "शाखा" },
  print: { en: "Print / Save as PDF", mr: "छापा / PDF जतन करा", hi: "प्रिंट / PDF सहेजें" },
  loading: { en: "Loading…", mr: "लोड होत आहे…", hi: "लोड हो रहा है…" },
  amendments: { en: "Amendments are versioned; this copy is immutable.", mr: "दुरुस्त्या आवृत्तीनुसार; ही प्रत अपरिवर्तनीय आहे.", hi: "संशोधन संस्करण में हैं; यह प्रति अपरिवर्तनीय है।" },
  acknowledged: { en: "acknowledged by prescriber", mr: "डॉक्टरांनी नोंद घेतली", hi: "चिकित्सक द्वारा स्वीकार" },
};

function tri(l: Label) {
  return (
    <>
      {l.en} <span className="tri">/ {l.mr} / {l.hi}</span>
    </>
  );
}

/** A4 / A5 (and 80 mm roll for receipts): pure print CSS, see lib/print-paper.ts. */
function PaperPicker({ paper, isReceipt }: { paper: Paper; isReceipt: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  return (
    <div className="no-print paper-picker" role="group" aria-label="Paper / कागद / कागज़">
      {papersFor(isReceipt).map((p) => (
        <button
          key={p}
          type="button"
          aria-pressed={p === paper}
          data-testid={`paper-${p}`}
          onClick={() => {
            const q = new URLSearchParams(search.toString());
            q.set("paper", p);
            router.replace(`${pathname}?${q.toString()}`);
          }}
        >
          {PAPER_LABEL[p].en}
          {PAPER_LABEL[p].mr !== PAPER_LABEL[p].en && <span className="tri"> / {PAPER_LABEL[p].mr}</span>}
        </button>
      ))}
    </div>
  );
}

export default function PrintPage() {
  return (
    <Suspense fallback={null}>
      <PrintView />
    </Suspense>
  );
}

function PrintView() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const type = search.get("type") === "receipt" ? "receipt" : "rx";
  const paper = parsePaper(search.get("paper"), type === "receipt");
  const sheetClass = `print-sheet paper-${paper}`;
  const css = PRINT_CSS + pageCss(paper);

  const [rx, setRx] = useState<PrescriptionDetail | null>(null);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [drugs, setDrugs] = useState<Record<string, Drug>>({});
  const [me, setMe] = useState<Me | null>(null);
  const [branchName, setBranchName] = useState<string>("");
  const [prescriber, setPrescriber] = useState<Prescriber | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => onAuthFailure(() => router.replace("/login")), [router]);

  useEffect(() => {
    async function load() {
      try {
        if (type === "receipt") {
          const r = await api.get<Receipt>(`/billing/invoices/${params.id}/receipt`);
          setReceipt(r);
          return;
        }
        const [detail, who] = await Promise.all([
          api.get<PrescriptionDetail>(`/prescriptions/${params.id}`),
          api.get<Me>("/auth/me"),
        ]);
        setRx(detail);
        setMe(who);
        // Perf: patient and encounter in parallel (was a request waterfall).
        const encounterBranch = detail.encounter_id
          ? api
              .get<EncounterDetail>(`/encounters/${detail.encounter_id}`)
              .then((e) => ({ ok: true as const, id: e.branch_id }))
              .catch(() => ({ ok: false as const, id: null }))
          : Promise.resolve({ ok: false as const, id: null });
        setPatient(await api.get<Patient>(`/patients/${detail.patient_id}`));

        // Clinic branch: the encounter's branch, else the viewer's own branch.
        let branchId = who.branch_id;
        const enc = await encounterBranch;
        if (enc.ok) branchId = enc.id;
        if (branchId) {
          api
            .get<Branch>(`/branches/${branchId}`)
            .then((b) => setBranchName(b.name))
            .catch(() => undefined);
        }

        // Prescriber identity: Rx detail (M7 contract) first, then fallbacks.
        if (detail.prescriber) {
          setPrescriber(detail.prescriber);
        } else if (detail.prescriber_user_id) {
          if (detail.prescriber_user_id === who.user.id) {
            setPrescriber({ user_id: who.user.id, full_name: who.user.full_name, registration_number: null });
          } else {
            api
              .get<Member[]>("/members")
              .then((ms) => {
                const m = ms.find((x) => x.user_id === detail.prescriber_user_id);
                if (m) setPrescriber({ user_id: m.user_id, full_name: m.full_name, registration_number: null });
              })
              .catch(() => undefined);
          }
        }

        // Catalog fallback only when the Rx detail lacks names (pre-M7 API).
        if (detail.items.some((it) => !it.drug_name && !it.generic_name)) {
          const catalog = await api.get<Drug[]>("/prescriptions/drugs?limit=200");
          setDrugs(Object.fromEntries(catalog.map((d) => [d.id, d])));
        }
      } catch (err) {
        setError(err instanceof ApiError ? String(err.message) : "Load failed");
      }
    }
    void load();
  }, [params.id, type]);

  if (error) {
    return (
      <main className={sheetClass}>
        <p className="error">{error}</p>
      </main>
    );
  }

  if (type === "receipt" && receipt) {
    const inv = receipt.invoice;
    return (
      <main className={sheetClass}>
        <header className="print-head">
          <div>
            <h1>{receipt.org_name}</h1>
            <p className="tri">
              {receipt.branch_name} — {tri(L.receipt)}
            </p>
          </div>
          <div style={{ textAlign: "right" }}>
            <p>
              <strong>{inv.invoice_number}</strong>
            </p>
            <p>{new Date(inv.created_at).toLocaleDateString("en-IN")}</p>
          </div>
        </header>

        <section className="print-meta">
          <p>
            {tri(L.patient)}: <strong>{receipt.patient_name}</strong>
          </p>
          <p>
            {tri(L.uhid)}: <strong>{receipt.patient_uhid}</strong>
          </p>
        </section>

        <table className="print-table">
          <thead>
            <tr>
              <th>{tri(L.items)}</th>
              <th>{tri(L.qty)}</th>
              <th>{tri(L.rate)}</th>
              <th>{tri(L.amount)}</th>
            </tr>
          </thead>
          <tbody>
            {receipt.items.map((it) => (
              <tr key={it.id}>
                <td>
                  {it.description} <span className="tri">({it.item_type})</span>
                </td>
                <td>{it.quantity}</td>
                <td>{Number(it.unit_price).toFixed(2)}</td>
                <td>{Number(it.line_total).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <section className="print-totals">
          <p>
            {tri(L.total)}: <strong>{Number(inv.total).toFixed(2)}</strong>
          </p>
          <p>
            {tri(L.paid)}: <strong>{Number(inv.amount_paid).toFixed(2)}</strong>
          </p>
          <p>
            {tri(L.balance)}: <strong>{receipt.balance_due.toFixed(2)}</strong>
          </p>
        </section>

        {receipt.payments.length > 0 && (
          <section>
            <h3>{tri(L.payment)}</h3>
            <ul>
              {receipt.payments.map((p) => (
                <li key={p.id}>
                  {Number(p.amount).toFixed(2)} — {p.method} ({p.status})
                </li>
              ))}
            </ul>
          </section>
        )}

        <footer className="print-foot">
          <span>{tri(L.signature)}</span>
        </footer>
        <PaperPicker paper={paper} isReceipt />
        <button
          type="button"
          className="no-print"
          onClick={() => window.print()}
          style={{ margin: "1rem auto", display: "block" }}
        >
          {tri(L.print)}
        </button>
        <style>{css}</style>
      </main>
    );
  }

  if (!rx || !patient) {
    return (
      <main className={sheetClass}>
        <p className="muted">{tri(L.loading)}</p>
        <style>{css}</style>
      </main>
    );
  }

  return (
    <main className={sheetClass}>
      <header className="print-head">
        <div>
          <h1 data-testid="clinic-name">{me?.organization.name ?? ""}</h1>
          {branchName && (
            <p className="tri" data-testid="clinic-branch">
              {tri(L.branch)}: {branchName}
            </p>
          )}
          <p className="doc-title">{tri(L.prescription)}</p>
        </div>
        <div style={{ textAlign: "right" }}>
          <p>
            {tri(L.date)}: {new Date(rx.signed_at ?? rx.created_at).toLocaleDateString("en-IN")}
          </p>
          <p>
            {tri(L.version)}: v{rx.version}
          </p>
        </div>
      </header>

      <section className="print-meta">
        <p>
          {tri(L.patient)}: <strong>{patient.full_name}</strong>
        </p>
        <p>
          {tri(L.uhid)}: <strong>{patient.uhid}</strong> · {patient.gender} ·{" "}
          {patient.date_of_birth
            ? new Date(patient.date_of_birth).toLocaleDateString("en-IN")
            : "—"}
        </p>
        {patient.allergies && (
          <p className="error">
            ⚠ {tri(L.allergies)}: <strong>{patient.allergies}</strong>
            {rx.allergy_acknowledged && <> ({tri(L.acknowledged)})</>}
          </p>
        )}
        {rx.diagnosis_text && (
          <p>
            {tri(L.diagnosis)}: <strong>{rx.diagnosis_text}</strong>
          </p>
        )}
      </section>

      <table className="print-table">
        <thead>
          <tr>
            <th>#</th>
            <th>{tri(L.medicines)}</th>
            <th>{tri(L.dose)}</th>
            <th>{tri(L.route)}</th>
            <th>{tri(L.frequency)}</th>
            <th>{tri(L.days)}</th>
            <th>{tri(L.qtyDispense)}</th>
          </tr>
        </thead>
        <tbody>
          {rx.items.map((it, i) => {
            const n = itemDrugName(it, drugs);
            return (
              <tr key={it.id} data-testid="rx-print-item">
                <td>{i + 1}</td>
                <td>
                  <strong>{n.name}</strong>
                  {n.detail && <span className="tri"> ({n.detail})</span>}
                  {it.instructions && <div className="tri">{it.instructions}</div>}
                </td>
                <td data-testid="rx-print-dose">{it.dose}</td>
                <td>{it.route}</td>
                <td>{it.frequency}</td>
                <td>{it.duration_days}</td>
                <td>{it.dispense_quantity ?? it.quantity ?? ""}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <section className="print-advice">
        {rx.advice && (
          <p>
            {tri(L.advice)}: {rx.advice}
          </p>
        )}
        {rx.follow_up && (
          <p>
            {tri(L.followUp)}: {rx.follow_up}
          </p>
        )}
        <p className="tri">{tri(L.amendments)}</p>
      </section>

      <footer className="print-foot">
        <div className="prescriber" data-testid="prescriber">
          {prescriber && (
            <>
              <p>
                <strong>{prescriber.full_name}</strong>
              </p>
              <p className="tri">
                {tri(L.regNo)}: {prescriber.registration_number || "—"}
              </p>
            </>
          )}
          <p>{tri(L.signature)}</p>
        </div>
      </footer>

      <PaperPicker paper={paper} isReceipt={false} />
      <button
        type="button"
        className="no-print"
        onClick={() => window.print()}
        style={{ margin: "1rem auto", display: "block" }}
      >
        {tri(L.print)}
      </button>

      <style>{css}</style>
    </main>
  );
}

const PRINT_CSS = `
  .print-sheet { font-family: Georgia, "Noto Serif", serif; color: #101828;
    max-width: 800px; margin: 0 auto; padding: 1.5rem; background: #fff; }
  .print-head { display: flex; justify-content: space-between;
    border-bottom: 3px double #1d3557; padding-bottom: 0.5rem; }
  .print-head h1 { font-size: 1.4rem; margin: 0; color: #1d3557;
    letter-spacing: 0.05em; }
  .tri { color: #486581; font-size: 0.85em; font-weight: normal; }
  .print-meta { margin: 0.75rem 0; }
  .print-meta p { margin: 0.2rem 0; }
  .print-table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; }
  .print-table th, .print-table td { border: 1px solid #bcccdc;
    padding: 0.4rem 0.5rem; text-align: left; font-size: 0.95rem; }
  .print-table th { background: #f0f4f8; }
  .print-advice { margin-top: 0.75rem; }
  .print-totals { text-align: right; margin-top: 0.5rem; }
  .print-totals p { margin: 0.15rem 0; }
  .print-foot { margin-top: 2.5rem; display: flex; justify-content: flex-end;
    border-top: 1px solid #bcccdc; padding-top: 0.5rem; }
  @media print {
    .no-print { display: none !important; }
    .print-sheet { max-width: none; padding: 0; }
  }
  .doc-title { margin: 0.2rem 0 0; font-weight: bold; color: #1d3557; }
  .prescriber { text-align: right; }
  .prescriber p { margin: 0.1rem 0; }
  .paper-picker { display: flex; gap: 0.4rem; justify-content: center; flex-wrap: wrap; margin-top: 1rem; }
  .paper-picker button { min-height: 40px; padding: 0.3rem 0.8rem; border: 1px solid #486581;
    border-radius: 8px; background: #fff; color: #101828; cursor: pointer; }
  .paper-picker button[aria-pressed="true"] { background: #1d3557; color: #fff; }
  .paper-picker button[aria-pressed="true"] .tri { color: #dbe7f3; }
`;
