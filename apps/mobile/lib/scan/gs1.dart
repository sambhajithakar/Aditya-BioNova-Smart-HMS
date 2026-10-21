/// Minimal GS1 element-string parser for medicine batch barcodes
/// (GS1 DataMatrix / GS1-128 as printed on Indian pharma packs).
///
/// Supported Application Identifiers: (01) GTIN-14, (10) batch/lot,
/// (11) production date, (17) expiry date, (21) serial. Accepts the raw
/// scanner output (FNC1 as ASCII 29 `GS`, optional `]d2` / `]C1` / `]Q3`
/// symbology prefix) and the human-readable "(01)…(17)…(10)…" form.
/// Anything else is returned as a plain code (an in-house SKU label).
library;

class Gs1Data {
  const Gs1Data({
    this.gtin,
    this.batch,
    this.expiry,
    this.productionDate,
    this.serial,
    required this.raw,
  });

  final String? gtin;
  final String? batch;
  final DateTime? expiry;
  final DateTime? productionDate;
  final String? serial;
  final String raw;

  bool get isGs1 => gtin != null || batch != null || expiry != null;

  /// `yyyy-mm-dd` (for display and the count draft), or ''.
  String get expiryText => expiry == null
      ? ''
      : '${expiry!.year.toString().padLeft(4, '0')}-'
          '${expiry!.month.toString().padLeft(2, '0')}-'
          '${expiry!.day.toString().padLeft(2, '0')}';
}

const String _gs = '\u001d';

Gs1Data parseGs1(String input) {
  var s = input.trim();
  for (final prefix in [']d2', ']C1', ']Q3', ']e0']) {
    if (s.startsWith(prefix)) {
      s = s.substring(prefix.length);
      break;
    }
  }
  if (s.startsWith('(')) {
    // "(01)0890…(17)271231(10)AB12" → GS-separated form
    final parts = RegExp(r'\((\d{2,4})\)([^(]*)').allMatches(s);
    s = parts.map((m) => '${m.group(1)}${m.group(2)}').join(_gs);
  }
  if (s.startsWith(_gs)) s = s.substring(1);

  String? gtin;
  String? batch;
  String? serial;
  DateTime? expiry;
  DateTime? prod;
  var i = 0;
  var recognised = true;
  while (i < s.length && recognised) {
    if (i + 2 > s.length) break;
    final ai = s.substring(i, i + 2);
    i += 2;
    String fixed(int n) {
      if (i + n > s.length) {
        recognised = false;
        return '';
      }
      final v = s.substring(i, i + n);
      i += n;
      if (i < s.length && s[i] == _gs) i += 1;
      return v;
    }

    String variable(int max) {
      var end = s.indexOf(_gs, i);
      if (end < 0) end = s.length;
      if (end - i > max) end = i + max;
      final v = s.substring(i, end);
      i = end;
      if (i < s.length && s[i] == _gs) i += 1;
      return v;
    }

    switch (ai) {
      case '01':
        final v = fixed(14);
        if (RegExp(r'^\d{14}$').hasMatch(v)) {
          gtin = v;
        } else {
          recognised = false;
        }
      case '17':
        expiry = _yymmdd(fixed(6));
      case '11':
        prod = _yymmdd(fixed(6));
      case '10':
        batch = variable(20);
      case '21':
        serial = variable(20);
      default:
        recognised = false;
    }
  }
  if (!recognised && gtin == null && batch == null) {
    return Gs1Data(raw: input.trim());
  }
  return Gs1Data(
    gtin: gtin,
    batch: batch,
    expiry: expiry,
    productionDate: prod,
    serial: serial,
    raw: input.trim(),
  );
}

/// GS1 YYMMDD; DD = 00 means the last day of the month.
DateTime? _yymmdd(String v) {
  if (!RegExp(r'^\d{6}$').hasMatch(v)) return null;
  final yy = int.parse(v.substring(0, 2));
  final mm = int.parse(v.substring(2, 4));
  final dd = int.parse(v.substring(4, 6));
  if (mm < 1 || mm > 12) return null;
  // GS1 century rule (simplified): 2000–2099 for our time frame.
  final year = 2000 + yy;
  if (dd == 0) return DateTime.utc(year, mm + 1, 0);
  final d = DateTime.utc(year, mm, dd);
  return d.month == mm ? d : null;
}
