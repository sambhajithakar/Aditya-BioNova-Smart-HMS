/**
 * Minimal inline line icons for the phone bottom bar (hand-drawn paths, no
 * third-party icon set). Decorative: the label next to each icon is the
 * accessible name.
 */
const P: Record<string, string> = {
  dashboard: "M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  patients: "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21v-1a6 6 0 0 1 12 0v1M16 3.5a4 4 0 0 1 0 7.5M22 21v-1a6 6 0 0 0-4-5.6",
  appointments: "M4 5h16v16H4zM4 9h16M8 3v4M16 3v4",
  queue: "M4 6h16M4 12h16M4 18h10",
  consultation: "M6 3v6a4 4 0 0 0 8 0V3M10 13v3a5 5 0 0 0 10 0v-2M20 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  billing: "M6 2h12v20l-3-2-3 2-3-2-3 2zM9 7h6M9 11h6M9 15h4",
  pharmacy: "M10.5 3.5a5 5 0 0 1 7 7l-7 7a5 5 0 0 1-7-7zM7 7l10 10",
  lab: "M9 3h6M10 3v6L4 19a1.5 1.5 0 0 0 1.3 2h13.4A1.5 1.5 0 0 0 20 19l-6-10V3M7 14h10",
  ipd: "M3 18V7M3 14h18v4M21 14v-2a3 3 0 0 0-3-3h-7v5M7 11.5a1.5 1.5 0 1 0 0-.01",
  inventory: "M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10",
  expenses: "M3 6h18v12H3zM3 10h18M7 15h3",
  reports: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-5-5",
  more: "M5 12h.01M12 12h.01M19 12h.01",
};

export function NavIcon({ name }: { name: string }) {
  const d = P[name] ?? "M12 12m-4 0a4 4 0 1 0 8 0a4 4 0 1 0-8 0";
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={name === "more" ? 3.2 : 1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={d} />
    </svg>
  );
}
