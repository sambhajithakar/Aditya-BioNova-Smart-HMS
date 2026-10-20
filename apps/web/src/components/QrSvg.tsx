"use client";

import { useMemo } from "react";
import { encodeQr, qrSvgPath } from "@/lib/qr";

/** Inline-SVG QR code (crisp at any print size; no image URLs needed). */
export function QrSvg({ value, size = 220, label }: { value: string; size?: number; label: string }) {
  const svg = useMemo(() => qrSvgPath(encodeQr(value, { ecl: "M" }), 4), [value]);
  return (
    <svg
      role="img"
      aria-label={label}
      width={size}
      height={size}
      viewBox={svg.viewBox}
      shapeRendering="crispEdges"
      style={{ background: "#fff", display: "block" }}
      data-testid="checkin-qr"
    >
      <rect width="100%" height="100%" fill="#fff" />
      <path d={svg.path} fill="#000" />
    </svg>
  );
}
