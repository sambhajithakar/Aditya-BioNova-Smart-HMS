/// Inventory count drafts (pharmacy / store room), scanned or typed.
///
/// A count is ONLY a draft on the device: it records what was physically
/// counted, the item it was matched to (by SKU / GTIN from a scanned batch
/// barcode) and the batch / expiry read from the barcode. It is never
/// queued for automatic sync — a stock adjustment changes the books, so it
/// is posted ONLINE, after the user reviewed the difference against the
/// server's current quantity-on-hand, with its own Idempotency-Key
/// (`HmsClient.postStockAdjustment`).
library;

import '../store/local_store.dart';
import '../sync/outbox.dart' show Outbox;
import 'rx_drafts.dart' show DirectoryList;

class StockCountBook {
  StockCountBook(this.store);

  static const String section = 'stock_counts';

  /// Bounded: a count session rarely exceeds a few hundred lines.
  static const int maxCounts = 2000;

  final LocalStore store;
  List<Map<String, dynamic>> counts = <Map<String, dynamic>>[];

  /// Inventory items cached for matching barcodes offline (no PHI).
  List<Map<String, dynamic>> items = <Map<String, dynamic>>[];

  void load() {
    final raw = store.doc[section];
    if (raw is! Map<String, dynamic>) return;
    counts = DirectoryList.of(raw['counts']);
    items = DirectoryList.of(raw['items']);
  }

  Future<void> save() =>
      store.saveSection(section, {'counts': counts, 'items': items});

  Future<void> clear() async {
    counts = <Map<String, dynamic>>[];
    items = <Map<String, dynamic>>[];
    await store.saveSection(section, null);
  }

  Future<void> replaceItems(List<Map<String, dynamic>> next) async {
    items = next;
    await save();
  }

  /// Match a scanned code: exact SKU, or the GTIN inside a GS1 code.
  Map<String, dynamic>? matchItem({String? sku, String? gtin}) {
    for (final it in items) {
      final s = (it['sku'] as String?) ?? '';
      if (s.isEmpty) continue;
      if (sku != null && s == sku) return it;
      if (gtin != null && (s == gtin || s == gtin.replaceFirst(RegExp('^0+'), ''))) {
        return it;
      }
    }
    return null;
  }

  Future<Map<String, dynamic>> addCount({
    required String itemId,
    required String itemName,
    required int counted,
    String batch = '',
    String expiry = '',
    String code = '',
  }) async {
    final entry = {
      'id': Outbox.newId(),
      'itemId': itemId,
      'itemName': itemName,
      'counted': counted,
      'batch': batch,
      'expiry': expiry,
      'code': code,
      'posted': false,
      'createdAt': DateTime.now().toUtc().toIso8601String(),
    };
    counts = [entry, ...counts];
    if (counts.length > maxCounts) counts = counts.sublist(0, maxCounts);
    await save();
    return entry;
  }

  Future<void> markPosted(String id) async {
    for (final c in counts) {
      if (c['id'] == id) c['posted'] = true;
    }
    await save();
  }

  Future<void> remove(String id) async {
    counts = [for (final c in counts) if (c['id'] != id) c];
    await save();
  }

  /// Unposted counts (kept in the quarantine on revocation).
  List<Map<String, dynamic>> get unposted =>
      [for (final c in counts) if (c['posted'] != true) c];

  Future<void> restore(List<Map<String, dynamic>> restored) async {
    final known = {for (final c in counts) c['id']};
    counts = [
      for (final c in restored)
        if (!known.contains(c['id'])) c,
      ...counts,
    ];
    await save();
  }
}
