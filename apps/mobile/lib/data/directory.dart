/// Directory cache: the slice of the server the app needs to work with no
/// network — patients, branches and the validated drug catalog.
///
/// Loaded at start-up from the encrypted [LocalStore] (that is what makes
/// "connect once, then work offline" true), refreshed whenever a list
/// endpoint succeeds, and updated with locally registered patients the
/// moment they are queued so reception can put a walk-in into today's queue
/// without ever having synced.
library;

import '../store/local_store.dart';
import '../sync/idmap.dart';

class DirectoryCache {
  DirectoryCache(this.store, {DateTime Function()? clock})
      : _clock = clock ?? (() => DateTime.now().toUtc());

  static const String section = 'directory';

  /// Bounded PHI cache (low-cost phones, least data at rest): at most this
  /// many SERVER patients — only ones this user already fetched online —
  /// newest first. Patients registered on this device and not yet synced
  /// are never evicted (they are unsynced work, not cache).
  static const int maxCachedPatients = 1000;

  /// Cached server patients older than this are dropped at start-up; the
  /// next online refresh fetches them again.
  static const Duration patientTtl = Duration(days: 7);

  final LocalStore store;
  final DateTime Function() _clock;

  /// When the server patient list was last refreshed.
  DateTime? patientsFetchedAt;

  List<Map<String, dynamic>> patients = <Map<String, dynamic>>[];
  List<Map<String, dynamic>> branches = <Map<String, dynamic>>[];
  List<Map<String, dynamic>> drugs = <Map<String, dynamic>>[];

  /// Every device id ever handed to a patient registered on this device.
  /// Lets [refFor] recognise a local id even after its directory entry was
  /// replaced by the server row — so a raw device UUID is NEVER sent as a
  /// `patient_id` (audit H24 / D6).
  final Set<String> localRefs = <String>{};

  /// Read the cache out of the already-open store document.
  void load() {
    final raw = store.doc[section];
    if (raw is! Map<String, dynamic>) return;
    patients = _list(raw['patients']);
    branches = _list(raw['branches']);
    drugs = _list(raw['drugs']);
    localRefs
      ..clear()
      ..addAll((raw['localRefs'] as List<dynamic>? ?? const [])
          .whereType<String>());
    for (final p in patients) {
      if (p['local'] == true && p['id'] is String) {
        localRefs.add(p['id'] as String);
      }
    }
    // Pre-M8 caches carry no timestamp: start their TTL now.
    patientsFetchedAt = raw['fetchedAt'] is String
        ? DateTime.tryParse(raw['fetchedAt'] as String)
        : null;
    patientsFetchedAt ??= _clock();
    if (_clock().difference(patientsFetchedAt!) > patientTtl) {
      patients = [for (final p in patients) if (p['local'] == true) p];
    }
  }

  Future<void> save() => store.saveSection(section, {
        'patients': patients,
        'branches': branches,
        'drugs': drugs,
        'localRefs': localRefs.toList(),
        'fetchedAt': patientsFetchedAt?.toIso8601String(),
      });

  /// Server patients currently cached (excludes device registrations).
  int get cachedServerPatients =>
      patients.where((p) => p['local'] != true).length;

  /// "Clear cached patient data": drop every cached SERVER patient; keep
  /// this device's unsynced registrations (they are work, not cache).
  Future<int> clearCachedPatients() async {
    final before = cachedServerPatients;
    patients = [for (final p in patients) if (p['local'] == true) p];
    await save();
    return before;
  }

  /// Add patients fetched by an online search to the bounded cache.
  Future<void> rememberFetched(List<Map<String, dynamic>> items) async {
    final ids = {for (final p in items) p['id']};
    final local = [for (final p in patients) if (p['local'] == true) p];
    final rest = [
      for (final p in patients)
        if (p['local'] != true && !ids.contains(p['id'])) p,
    ];
    patients = [...local, ..._bounded([...items, ...rest])];
    await save();
  }

  static List<Map<String, dynamic>> _bounded(List<Map<String, dynamic>> l) =>
      l.length <= maxCachedPatients ? l : l.sublist(0, maxCachedPatients);

  /// Local search of the cache (name, UHID or phone; case-insensitive).
  List<Map<String, dynamic>> search(String query) {
    final q = query.trim().toLowerCase();
    if (q.isEmpty) return patients;
    return [
      for (final p in patients)
        if (((p['full_name'] as String?) ?? '').toLowerCase().contains(q) ||
            ((p['uhid'] as String?) ?? '').toLowerCase().contains(q) ||
            ((p['phone'] as String?) ?? '').contains(q))
          p,
    ];
  }

  /// Device registrations not yet synced — moved to the quarantine when
  /// the device is revoked.
  List<Map<String, dynamic>> get localPatients =>
      [for (final p in patients) if (p['local'] == true) p];

  /// Put quarantined registrations back (the same user signed in again).
  Future<void> restoreLocalPatients(List<Map<String, dynamic>> items) async {
    for (final p in items.reversed) {
      final id = p['id'];
      if (id is! String || patientById(id) != null) continue;
      localRefs.add(id);
      patients = [p, ...patients];
    }
    await save();
  }

  /// Forget everything (sign-out / local reset).
  Future<void> clear() async {
    patients = <Map<String, dynamic>>[];
    branches = <Map<String, dynamic>>[];
    drugs = <Map<String, dynamic>>[];
    localRefs.clear();
    patientsFetchedAt = null;
    await store.saveSection(section, null);
  }

  /// Merge a fresh server patient list with the patients registered on
  /// this device (audit H24 / D6). A local entry is dropped only once its
  /// registration has synced AND the server list contains that patient;
  /// until then it stays, labelled "pending sync".
  Future<void> replacePatients(
    List<Map<String, dynamic>> items, {
    IdMap? idMap,
  }) async {
    final serverIds = {for (final p in items) p['id']};
    final keep = <Map<String, dynamic>>[];
    for (final p in patients) {
      if (p['local'] != true) continue;
      final ref = p['id'] as String?;
      if (ref == null) continue;
      final resolved = idMap?.serverIdOf(ref);
      if (resolved != null && serverIds.contains(resolved)) continue;
      keep.add(p);
    }
    patients = [...keep, ..._bounded(items)];
    patientsFetchedAt = _clock();
    await save();
  }

  /// Drop a locally registered patient whose registration was discarded.
  Future<void> removeLocalPatient(String localRef) async {
    patients = [
      for (final p in patients)
        if (!(p['local'] == true && p['id'] == localRef)) p,
    ];
    await save();
  }

  /// The id to put in an API payload for directory entry [id]: the server
  /// id once known, else the `$ref:` placeholder for a device-registered
  /// patient, else [id] itself (a server patient).
  String refFor(String id, IdMap idMap) {
    final server = idMap.serverIdOf(id);
    if (server != null) return server;
    final entry = patientById(id);
    if (localRefs.contains(id) || (entry != null && entry['local'] == true)) {
      return IdMap.placeholder(id);
    }
    return id;
  }

  /// Keep a picker selection valid after a refresh: [id] if still listed,
  /// its server id if the local entry was replaced by the server row. A
  /// selection that vanished (e.g. a discarded registration) becomes null
  /// — the user must pick again; it never silently becomes someone else.
  /// With no selection yet, the first patient is the default.
  String? resolveSelection(String? id, IdMap idMap) {
    if (id == null) {
      return patients.isNotEmpty ? patients.first['id'] as String? : null;
    }
    if (patientById(id) != null) return id;
    final server = idMap.serverIdOf(id);
    if (server != null && patientById(server) != null) return server;
    return null;
  }

  /// Picker label: server patients by UHID + name; device-registered ones
  /// flagged "(pending sync)" until the server has accepted them.
  /// The tags are passed in already translated by the UI.
  String pickerLabel(
    Map<String, dynamic> p,
    IdMap idMap, {
    String pendingTag = '(pending sync)',
    String syncedTag = '(synced)',
  }) {
    final id = p['id'] as String? ?? '';
    if (p['local'] == true) {
      final name = (p['full_name'] as String?) ?? '';
      return idMap.serverIdOf(id) == null
          ? '$name $pendingTag'
          : '$name $syncedTag';
    }
    return patientLabel(id);
  }

  Future<void> replaceBranches(List<Map<String, dynamic>> items) async {
    branches = items;
    await save();
  }

  Future<void> replaceDrugs(List<Map<String, dynamic>> items) async {
    drugs = items;
    await save();
  }

  /// Add a patient registered on this device BEFORE it reached the server.
  /// The entry carries the local ref as its `id` and an empty `uhid`; the
  /// sync engine maps the ref to the server id when the op is accepted.
  Future<void> addLocalPatient({
    required String localRef,
    required String fullName,
    required String gender,
    String phone = '',
  }) async {
    if (patientById(localRef) != null) return;
    localRefs.add(localRef);
    patients = [
      {
        'id': localRef,
        'uhid': '',
        'full_name': fullName,
        'gender': gender,
        'phone': phone,
        'local': true,
      },
      ...patients,
    ];
    await save();
  }

  Map<String, dynamic>? patientById(String id) {
    for (final p in patients) {
      if (p['id'] == id) return p;
    }
    return null;
  }

  String patientLabel(String id) {
    final p = patientById(id);
    if (p == null) return id;
    final uhid = (p['uhid'] as String?) ?? '';
    final name = (p['full_name'] as String?) ?? '';
    final label = '$uhid $name'.trim();
    return label.isEmpty ? id : label;
  }

  /// Normalize a JSON array of objects into typed maps.
  static List<Map<String, dynamic>> listOf(Object? raw) =>
      (raw as List<dynamic>? ?? const [])
          .whereType<Map<dynamic, dynamic>>()
          .map((e) => e.cast<String, dynamic>())
          .toList();

  static List<Map<String, dynamic>> _list(Object? raw) => listOf(raw);
}
