/// Calendar-day helpers.
///
/// Audit D12: "today" used to be the UTC date, so in India (UTC+5:30)
/// work done between 00:00 and 05:29 was filed under the previous day and
/// per-day duplicate prevention went wrong for early-morning (emergency)
/// work. The clinic day is the DEVICE-LOCAL calendar day (IST on the
/// clinic's phones).
library;

/// `yyyy-mm-dd` of [now] (default: the current time) in local time.
String localDay([DateTime? now]) {
  final d = (now ?? DateTime.now()).toLocal();
  String two(int v) => v.toString().padLeft(2, '0');
  return '${d.year.toString().padLeft(4, '0')}-${two(d.month)}-${two(d.day)}';
}
