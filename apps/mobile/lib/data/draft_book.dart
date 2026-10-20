/// A small list of drafts written on this device, kept in one section of
/// the encrypted store: consultation-note drafts (`consult_drafts`) and
/// appointment drafts (`appointment_drafts`).
///
/// Each draft has a `localRef` — the same ref as the outbox op that will
/// create it on the server — and a `serverId` once that op was accepted
/// (adopted from the [IdMap]). The draft list is what the screens show;
/// the outbox op is what syncs. Anything FINAL (completing a consultation)
/// is an online, server-verified action and never happens from here.
library;

import '../store/local_store.dart';
import '../sync/idmap.dart';
import 'rx_drafts.dart' show DirectoryList;

class DraftBook {
  DraftBook(this.store, this.section, {this.maxSynced = 50});

  final LocalStore store;
  final String section;

  /// Synced drafts are only a convenience copy of server data: keep at
  /// most this many (bounded storage on low-cost phones).
  final int maxSynced;

  List<Map<String, dynamic>> drafts = <Map<String, dynamic>>[];

  void load() {
    final raw = store.doc[section];
    if (raw is! Map<String, dynamic>) return;
    drafts = DirectoryList.of(raw['drafts']);
  }

  Future<void> save() => store.saveSection(section, {'drafts': drafts});

  Future<void> clear() async {
    drafts = <Map<String, dynamic>>[];
    await store.saveSection(section, null);
  }

  Map<String, dynamic>? byRef(String localRef) {
    for (final d in drafts) {
      if (d['localRef'] == localRef) return d;
    }
    return null;
  }

  Future<void> add(String localRef, Map<String, dynamic> fields) async {
    drafts = [
      {
        ...fields,
        'localRef': localRef,
        'serverId': null,
        'createdAt': DateTime.now().toUtc().toIso8601String(),
      },
      ...drafts,
    ];
    await save();
  }

  /// Update the fields of a draft (only while its op was never sent — the
  /// caller checks `OutboxOp.editable`).
  Future<void> update(String localRef, Map<String, dynamic> fields) async {
    final d = byRef(localRef);
    if (d == null) return;
    d.addAll(fields);
    await save();
  }

  Future<void> setFlag(String localRef, String flag) async {
    final d = byRef(localRef);
    if (d == null) return;
    d[flag] = true;
    await save();
  }

  Future<void> markDiscarded(Iterable<String> refs) async {
    final set = refs.toSet();
    var changed = false;
    for (final d in drafts) {
      if (set.contains(d['localRef']) && d['serverId'] == null) {
        d['discarded'] = true;
        changed = true;
      }
    }
    if (changed) await save();
  }

  Future<void> adoptSynced(IdMap ids) async {
    var changed = false;
    for (final d in drafts) {
      if (d['serverId'] != null) continue;
      final ref = d['localRef'];
      if (ref is! String) continue;
      final server = ids.serverIdOf(ref);
      if (server == null) continue;
      d['serverId'] = server;
      changed = true;
    }
    if (changed) {
      _trimSynced();
      await save();
    }
  }

  void _trimSynced() {
    var synced = 0;
    drafts = [
      for (final d in drafts)
        if (d['serverId'] == null || ++synced <= maxSynced) d,
    ];
  }

  /// Drafts not yet accepted by the server (quarantined on revocation).
  List<Map<String, dynamic>> get unsynced => [
        for (final d in drafts)
          if (d['serverId'] == null && d['discarded'] != true) d,
      ];

  /// Remove the unsynced drafts and return them; synced copies (server
  /// data) are dropped too — the device may no longer show them.
  Future<List<Map<String, dynamic>>> takeUnsyncedAndWipe() async {
    final out = unsynced;
    await clear();
    return out;
  }

  Future<void> restore(List<Map<String, dynamic>> items) async {
    final known = {for (final d in drafts) d['localRef']};
    drafts = [
      for (final d in items)
        if (!known.contains(d['localRef'])) d,
      ...drafts,
    ];
    await save();
  }
}
