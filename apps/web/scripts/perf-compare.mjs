#!/usr/bin/env node
/**
 * Compare two perf.spec.ts result files (medians) as a Markdown table.
 *   node scripts/perf-compare.mjs before.json after.json
 */
import { readFileSync } from "node:fs";

const [a, b] = process.argv.slice(2).map((p) => JSON.parse(readFileSync(p, "utf8")));
const keys = [
  ["loginJsBytes", "Login: JS transferred (bytes)"],
  ["loginFcp", "Login: FCP (ms)"],
  ["loginLcp", "Login: LCP (ms)"],
  ["loginLoad", "Login: load event (ms)"],
  ["signInToDashboardMs", "Sign in → dashboard heading (ms)"],
  ["dashboardJsBytes", "Sign-in step: JS transferred (bytes)"],
  ["nav_patientsMs", "Nav → Patients (ms)"],
  ["nav_queueMs", "Nav → Queue (ms)"],
  ["nav_consultationMs", "Nav → Consultation (ms)"],
  ["nav_billingMs", "Nav → Billing (ms)"],
  ["nav_pharmacyMs", "Nav → Pharmacy (ms)"],
  ["nav_labMs", "Nav → Lab (ms)"],
  ["nav_ipdMs", "Nav → IPD (ms)"],
  ["nav_reportsMs", "Nav → Reports (ms)"],
  ["navAllModulesMs", "All 8 module navigations (ms)"],
  ["data_patientsMs", "Nav → Patients: data loaded (ms)"],
  ["data_queueMs", "Nav → Queue: data loaded (ms)"],
  ["data_consultationMs", "Nav → Consultation: data loaded (ms)"],
  ["data_billingMs", "Nav → Billing: data loaded (ms)"],
  ["data_pharmacyMs", "Nav → Pharmacy: data loaded (ms)"],
  ["data_labMs", "Nav → Lab: data loaded (ms)"],
  ["data_ipdMs", "Nav → IPD: data loaded (ms)"],
  ["data_reportsMs", "Nav → Reports: data loaded (ms)"],
  ["dataAllModulesMs", "All 8 navigations, data loaded (ms)"],
  ["tbtMs", "Total blocking time (ms)"],
  ["heapUsedMB", "JS heap after GC (MB)"],
];
for (const profile of Object.keys(a)) {
  if (!b[profile]) continue;
  console.log(`\n#### ${profile}\n`);
  console.log("| Metric | Before | After | Change |");
  console.log("|---|---:|---:|---:|");
  for (const [k, label] of keys) {
    const x = a[profile].median[k];
    const y = b[profile].median[k];
    if (x === undefined || y === undefined) continue;
    const pct = x ? `${(((y - x) / x) * 100).toFixed(0)} %` : "—";
    console.log(`| ${label} | ${x} | ${y} | ${y - x > 0 ? "+" : ""}${pct} |`);
  }
}
