/** AI-1 pure helpers (no React), unit-tested in ai1.test.ts. */
export type ForecastPoint = {
  date: string;
  point: number;
  lo80: number;
  hi80: number;
  lo95: number;
  hi95: number;
};

/** Pure helper (unit-tested): map series to SVG coordinates. */
export function chartGeometry(
  history: { date: string; value: number }[],
  forecast: ForecastPoint[],
  width = 640,
  height = 200,
  pad = 28,
) {
  const n = history.length + forecast.length;
  const max = Math.max(1, ...history.map((h) => h.value), ...forecast.map((f) => f.hi95));
  const x = (i: number) => pad + (i * (width - 2 * pad)) / Math.max(1, n - 1);
  const y = (v: number) => height - pad - (v * (height - 2 * pad)) / max;
  const line = (pts: [number, number][]) =>
    pts.map(([a, b], i) => `${i ? "L" : "M"}${a.toFixed(1)},${b.toFixed(1)}`).join(" ");
  const off = history.length;
  return {
    max,
    history: line(history.map((h, i) => [x(i), y(h.value)])),
    forecast: line(forecast.map((f, i) => [x(off + i), y(f.point)])),
    band80:
      forecast.length === 0
        ? ""
        : line([
            ...forecast.map((f, i): [number, number] => [x(off + i), y(f.hi80)]),
            ...forecast.map((f, i): [number, number] => [x(off + i), y(f.lo80)]).reverse(),
          ]) + " Z",
    hi95: line(forecast.map((f, i) => [x(off + i), y(f.hi95)])),
    lo95: line(forecast.map((f, i) => [x(off + i), y(f.lo95)])),
    splitX: x(Math.max(0, off - 1)),
    width,
    height,
    pad,
  };
}

