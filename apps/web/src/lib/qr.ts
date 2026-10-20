/**
 * Minimal QR Code (Model 2) encoder — no third-party dependency.
 *
 * Scope: byte and alphanumeric mode, versions 1–40, error-correction levels
 * L/M/Q/H. That is ample for the check-in QR, which carries a 26-character
 * base32 token (alphanumeric mode, version 2 at level M).
 *
 * The algorithm follows ISO/IEC 18004 (structure as in Project Nayuki's
 * public-domain-style reference implementation). Output matrices are
 * verified module-for-module against the independent `segno` encoder in
 * qr.test.ts.
 */
export type Ecl = "L" | "M" | "Q" | "H";

export type QrCode = { version: number; size: number; mask: number; modules: boolean[][] };

const MAX_VERSION = 40;
const ECL_ORDINAL: Record<Ecl, number> = { L: 0, M: 1, Q: 2, H: 3 };
const ECL_FORMAT_BITS: Record<Ecl, number> = { L: 1, M: 0, Q: 3, H: 2 };
// index 0 unused; versions 1..40 (ISO/IEC 18004 Table 9)
const ECC_CODEWORDS_PER_BLOCK = [
  [-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28,
    30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
  [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28,
    28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28],
  [-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30,
    30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
  [-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30, 24,
    30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
];
const NUM_ERROR_CORRECTION_BLOCKS = [
  [-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13,
    14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25],
  [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23,
    25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49],
  [-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29,
    34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68],
  [-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35,
    37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81],
];
const ALNUM = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:";

function getBit(x: number, i: number): boolean {
  return ((x >>> i) & 1) !== 0;
}

function numRawDataModules(ver: number): number {
  let result = (16 * ver + 128) * ver + 64;
  if (ver >= 2) {
    const numAlign = Math.floor(ver / 7) + 2;
    result -= (25 * numAlign - 10) * numAlign - 55;
    if (ver >= 7) result -= 36;
  }
  return result;
}

function numDataCodewords(ver: number, ecl: Ecl): number {
  const e = ECL_ORDINAL[ecl];
  return (
    Math.floor(numRawDataModules(ver) / 8) -
    ECC_CODEWORDS_PER_BLOCK[e][ver] * NUM_ERROR_CORRECTION_BLOCKS[e][ver]
  );
}

// --- data segment -----------------------------------------------------------------
type Segment = { mode: "alnum" | "byte"; count: number; bits: number[] };

function utf8(text: string): number[] {
  return Array.from(new TextEncoder().encode(text));
}

function pushBits(out: number[], value: number, len: number): void {
  for (let i = len - 1; i >= 0; i--) out.push((value >>> i) & 1);
}

export function isAlphanumeric(text: string): boolean {
  return [...text].every((c) => ALNUM.includes(c));
}

function makeSegment(text: string): Segment {
  const bits: number[] = [];
  if (isAlphanumeric(text)) {
    let i = 0;
    for (; i + 2 <= text.length; i += 2) {
      pushBits(bits, ALNUM.indexOf(text[i]) * 45 + ALNUM.indexOf(text[i + 1]), 11);
    }
    if (i < text.length) pushBits(bits, ALNUM.indexOf(text[i]), 6);
    return { mode: "alnum", count: text.length, bits };
  }
  const bytes = utf8(text);
  for (const b of bytes) pushBits(bits, b, 8);
  return { mode: "byte", count: bytes.length, bits };
}

function charCountBits(mode: Segment["mode"], ver: number): number {
  if (mode === "alnum") return ver <= 9 ? 9 : ver <= 26 ? 11 : 13;
  return ver <= 9 ? 8 : 16;
}

function segmentBits(seg: Segment, ver: number): number {
  return 4 + charCountBits(seg.mode, ver) + seg.bits.length;
}

// --- Reed–Solomon over GF(2^8) / 0x11D --------------------------------------------
function rsMultiply(x: number, y: number): number {
  let z = 0;
  for (let i = 7; i >= 0; i--) {
    z = (z << 1) ^ ((z >>> 7) * 0x11d);
    z ^= ((y >>> i) & 1) * x;
  }
  return z & 0xff;
}

function rsDivisor(degree: number): number[] {
  const result = new Array<number>(degree).fill(0);
  result[degree - 1] = 1;
  let root = 1;
  for (let i = 0; i < degree; i++) {
    for (let j = 0; j < result.length; j++) {
      result[j] = rsMultiply(result[j], root);
      if (j + 1 < result.length) result[j] ^= result[j + 1];
    }
    root = rsMultiply(root, 0x02);
  }
  return result;
}

function rsRemainder(data: number[], divisor: number[]): number[] {
  const result = divisor.map(() => 0);
  for (const b of data) {
    const factor = b ^ (result.shift() as number);
    result.push(0);
    divisor.forEach((coef, i) => {
      result[i] ^= rsMultiply(coef, factor);
    });
  }
  return result;
}

function addEccAndInterleave(data: number[], ver: number, ecl: Ecl): number[] {
  const e = ECL_ORDINAL[ecl];
  const numBlocks = NUM_ERROR_CORRECTION_BLOCKS[e][ver];
  const blockEccLen = ECC_CODEWORDS_PER_BLOCK[e][ver];
  const rawCodewords = Math.floor(numRawDataModules(ver) / 8);
  const numShortBlocks = numBlocks - (rawCodewords % numBlocks);
  const shortBlockLen = Math.floor(rawCodewords / numBlocks);
  const div = rsDivisor(blockEccLen);
  const blocks: number[][] = [];
  for (let i = 0, k = 0; i < numBlocks; i++) {
    const dat = data.slice(k, k + shortBlockLen - blockEccLen + (i < numShortBlocks ? 0 : 1));
    k += dat.length;
    const ecc = rsRemainder(dat, div);
    if (i < numShortBlocks) dat.push(0);
    blocks.push(dat.concat(ecc));
  }
  const result: number[] = [];
  for (let i = 0; i < blocks[0].length; i++) {
    blocks.forEach((block, j) => {
      if (i !== shortBlockLen - blockEccLen || j >= numShortBlocks) result.push(block[i]);
    });
  }
  return result;
}

// --- matrix -------------------------------------------------------------------------
class Matrix {
  version: number;
  size: number;
  modules: boolean[][];
  isFunction: boolean[][];
  constructor(version: number) {
    this.version = version;
    this.size = version * 4 + 17;
    this.modules = Array.from({ length: this.size }, () => new Array<boolean>(this.size).fill(false));
    this.isFunction = Array.from({ length: this.size }, () =>
      new Array<boolean>(this.size).fill(false),
    );
  }

  setFunction(x: number, y: number, dark: boolean): void {
    this.modules[y][x] = dark;
    this.isFunction[y][x] = true;
  }

  alignmentPositions(): number[] {
    if (this.version === 1) return [];
    const numAlign = Math.floor(this.version / 7) + 2;
    const step =
      this.version === 32 ? 26 : Math.ceil((this.version * 4 + 4) / (numAlign * 2 - 2)) * 2;
    const result = [6];
    for (let pos = this.size - 7; result.length < numAlign; pos -= step) result.splice(1, 0, pos);
    return result;
  }

  drawFunctionPatterns(ecl: Ecl): void {
    for (let i = 0; i < this.size; i++) {
      this.setFunction(6, i, i % 2 === 0);
      this.setFunction(i, 6, i % 2 === 0);
    }
    this.finder(3, 3);
    this.finder(this.size - 4, 3);
    this.finder(3, this.size - 4);
    const pos = this.alignmentPositions();
    const n = pos.length;
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        if ((i === 0 && j === 0) || (i === 0 && j === n - 1) || (i === n - 1 && j === 0)) continue;
        for (let dy = -2; dy <= 2; dy++) {
          for (let dx = -2; dx <= 2; dx++) {
            this.setFunction(pos[i] + dx, pos[j] + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
          }
        }
      }
    }
    this.drawFormat(ecl, 0);
    this.drawVersion();
  }

  finder(x: number, y: number): void {
    for (let dy = -4; dy <= 4; dy++) {
      for (let dx = -4; dx <= 4; dx++) {
        const dist = Math.max(Math.abs(dx), Math.abs(dy));
        const xx = x + dx;
        const yy = y + dy;
        if (xx >= 0 && xx < this.size && yy >= 0 && yy < this.size) {
          this.setFunction(xx, yy, dist !== 2 && dist !== 4);
        }
      }
    }
  }

  drawFormat(ecl: Ecl, mask: number): void {
    const data = (ECL_FORMAT_BITS[ecl] << 3) | mask;
    let rem = data;
    for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
    const bits = ((data << 10) | rem) ^ 0x5412;
    for (let i = 0; i <= 5; i++) this.setFunction(8, i, getBit(bits, i));
    this.setFunction(8, 7, getBit(bits, 6));
    this.setFunction(8, 8, getBit(bits, 7));
    this.setFunction(7, 8, getBit(bits, 8));
    for (let i = 9; i < 15; i++) this.setFunction(14 - i, 8, getBit(bits, i));
    for (let i = 0; i < 8; i++) this.setFunction(this.size - 1 - i, 8, getBit(bits, i));
    for (let i = 8; i < 15; i++) this.setFunction(8, this.size - 15 + i, getBit(bits, i));
    this.setFunction(8, this.size - 8, true);
  }

  drawVersion(): void {
    if (this.version < 7) return;
    let rem = this.version;
    for (let i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1f25);
    const bits = (this.version << 12) | rem;
    for (let i = 0; i < 18; i++) {
      const bit = getBit(bits, i);
      const a = this.size - 11 + (i % 3);
      const b = Math.floor(i / 3);
      this.setFunction(a, b, bit);
      this.setFunction(b, a, bit);
    }
  }

  drawCodewords(data: number[]): void {
    let i = 0;
    for (let right = this.size - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5;
      for (let vert = 0; vert < this.size; vert++) {
        for (let j = 0; j < 2; j++) {
          const x = right - j;
          const upward = ((right + 1) & 2) === 0;
          const y = upward ? this.size - 1 - vert : vert;
          if (!this.isFunction[y][x] && i < data.length * 8) {
            this.modules[y][x] = getBit(data[i >>> 3], 7 - (i & 7));
            i++;
          }
        }
      }
    }
  }

  applyMask(mask: number): void {
    for (let y = 0; y < this.size; y++) {
      for (let x = 0; x < this.size; x++) {
        let invert: boolean;
        switch (mask) {
          case 0: invert = (x + y) % 2 === 0; break;
          case 1: invert = y % 2 === 0; break;
          case 2: invert = x % 3 === 0; break;
          case 3: invert = (x + y) % 3 === 0; break;
          case 4: invert = (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0; break;
          case 5: invert = ((x * y) % 2) + ((x * y) % 3) === 0; break;
          case 6: invert = (((x * y) % 2) + ((x * y) % 3)) % 2 === 0; break;
          default: invert = (((x + y) % 2) + ((x * y) % 3)) % 2 === 0;
        }
        if (!this.isFunction[y][x] && invert) this.modules[y][x] = !this.modules[y][x];
      }
    }
  }

  /** ISO penalty score (N1 runs, N2 blocks, N3 finder-like, N4 balance). */
  penalty(): number {
    const m = this.modules;
    const n = this.size;
    let score = 0;
    const line = (get: (i: number) => boolean) => {
      let s = 0;
      let run = 1;
      for (let i = 1; i < n; i++) {
        if (get(i) === get(i - 1)) {
          run++;
        } else {
          if (run >= 5) s += run - 2;
          run = 1;
        }
      }
      if (run >= 5) s += run - 2;
      // 1:1:3:1:1 with 4 light modules on either side (out of bounds = light)
      const at = (i: number) => (i < 0 || i >= n ? false : get(i));
      for (let i = -4; i < n; i++) {
        const core = [true, false, true, true, true, false, true];
        if (!core.every((d, k) => at(i + k) === d)) continue;
        const before = [1, 2, 3, 4].every((k) => !at(i - k));
        const after = [7, 8, 9, 10].every((k) => !at(i + k));
        if (before || after) s += 40;
      }
      return s;
    };
    for (let y = 0; y < n; y++) score += line((x) => m[y][x]);
    for (let x = 0; x < n; x++) score += line((y) => m[y][x]);
    for (let y = 0; y < n - 1; y++) {
      for (let x = 0; x < n - 1; x++) {
        const c = m[y][x];
        if (c === m[y][x + 1] && c === m[y + 1][x] && c === m[y + 1][x + 1]) score += 3;
      }
    }
    let dark = 0;
    for (const row of m) for (const c of row) if (c) dark++;
    const total = n * n;
    const k = Math.ceil(Math.abs(dark * 20 - total * 10) / total) - 1;
    return score + Math.max(0, k) * 10;
  }
}

/** Encode `text` as a QR code. `mask` forces a mask pattern (0–7). */
export function encodeQr(text: string, opts: { ecl?: Ecl; mask?: number } = {}): QrCode {
  const ecl = opts.ecl ?? "M";
  const seg = makeSegment(text);
  let ver = 1;
  for (; ver <= MAX_VERSION; ver++) {
    if (segmentBits(seg, ver) <= numDataCodewords(ver, ecl) * 8) break;
  }
  if (ver > MAX_VERSION) throw new Error("QR payload too long");

  const capacity = numDataCodewords(ver, ecl) * 8;
  const bits: number[] = [];
  pushBits(bits, seg.mode === "alnum" ? 0x2 : 0x4, 4);
  pushBits(bits, seg.count, charCountBits(seg.mode, ver));
  bits.push(...seg.bits);
  pushBits(bits, 0, Math.min(4, capacity - bits.length));
  pushBits(bits, 0, (8 - (bits.length % 8)) % 8);
  for (let pad = 0xec; bits.length < capacity; pad ^= 0xec ^ 0x11) pushBits(bits, pad, 8);
  const data: number[] = [];
  for (let i = 0; i < bits.length; i += 8) {
    data.push(bits.slice(i, i + 8).reduce((acc, b) => (acc << 1) | b, 0));
  }
  const codewords = addEccAndInterleave(data, ver, ecl);

  const build = (mask: number) => {
    const mtx = new Matrix(ver);
    mtx.drawFunctionPatterns(ecl);
    mtx.drawCodewords(codewords);
    mtx.applyMask(mask);
    mtx.drawFormat(ecl, mask);
    return mtx;
  };

  let best: Matrix;
  let bestMask: number;
  if (opts.mask !== undefined) {
    if (!Number.isInteger(opts.mask) || opts.mask < 0 || opts.mask > 7) {
      throw new Error("mask must be 0-7");
    }
    best = build(opts.mask);
    bestMask = opts.mask;
  } else {
    best = build(0);
    bestMask = 0;
    let bestScore = best.penalty();
    for (let mask = 1; mask < 8; mask++) {
      const cand = build(mask);
      const s = cand.penalty();
      if (s < bestScore) {
        best = cand;
        bestMask = mask;
        bestScore = s;
      }
    }
  }
  return { version: ver, size: best.size, mask: bestMask, modules: best.modules };
}

/** SVG path data (one unit per module) with a `border`-module quiet zone. */
export function qrSvgPath(qr: QrCode, border = 4): { path: string; viewBox: string } {
  const parts: string[] = [];
  qr.modules.forEach((row, y) =>
    row.forEach((dark, x) => {
      if (dark) parts.push(`M${x + border},${y + border}h1v1h-1z`);
    }),
  );
  const dim = qr.size + border * 2;
  return { path: parts.join(""), viewBox: `0 0 ${dim} ${dim}` };
}
