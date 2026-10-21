/// The clinic's registered devices (cached for offline capture) and which of
/// them are paired with THIS phone (M8.2).
///
/// A pairing is the Bluetooth address of the physical device the user chose
/// for a registered entry; the server confirms the match
/// (`POST /devices/{id}/verify-address`) and checks it again on every
/// reading. The server never returns addresses, so they live only here.
/// No patient data is stored in this section.
library;

import '../api/client.dart';
import '../api/transport.dart' show ApiException;
import '../store/local_store.dart';
import '../sync/idmap.dart';
import '../sync/outbox.dart';
import 'gatt.dart';
import 'transport.dart';

class DeviceBook {
  DeviceBook(this.store);

  static const String section = 'devices';

  final LocalStore store;
  List<Map<String, dynamic>> devices = <Map<String, dynamic>>[];

  /// registered device id -> {address, pairedAt}
  Map<String, Map<String, dynamic>> pairings = {};

  void load() {
    final raw = store.doc[section];
    if (raw is! Map<String, dynamic>) return;
    devices = [
      for (final d in (raw['devices'] as List? ?? const []))
        if (d is Map<String, dynamic>) d,
    ];
    final p = raw['pairings'];
    if (p is Map<String, dynamic>) {
      pairings = {
        for (final e in p.entries)
          if (e.value is Map<String, dynamic>) e.key: e.value as Map<String, dynamic>,
      };
    }
  }

  Future<void> save() => store.saveSection(
      section, {'devices': devices, 'pairings': pairings});

  Future<void> clear() async {
    devices = <Map<String, dynamic>>[];
    pairings = {};
    await store.saveSection(section, null);
  }

  List<Map<String, dynamic>> active({String? kind}) => [
        for (final d in devices)
          if (d['status'] == 'active' && (kind == null || d['kind'] == kind)) d,
      ];

  String? addressOf(String deviceId) => pairings[deviceId]?['address'] as String?;

  bool isPaired(String deviceId) => addressOf(deviceId) != null;

  /// `GET /devices` (online); keeps pairings only for still-active devices.
  Future<void> refresh(HmsClient client) async {
    final json = await client.request('GET', '/devices');
    if (json is! List) throw ApiException(200, 'Unexpected /devices response');
    devices = [for (final d in json) if (d is Map<String, dynamic>) d];
    final ids = {for (final d in active()) d['id']};
    pairings.removeWhere((id, _) => !ids.contains(id));
    await save();
  }

  /// Pair [deviceId] with the device at [address] after the server confirms
  /// it is the registered one. Returns false when it is not.
  Future<bool> pair(HmsClient client, String deviceId, String address) async {
    final res = await client.requestMap(
        'POST', '/devices/$deviceId/verify-address',
        body: {'ble_address': address});
    if (res['match'] != true || res['active'] != true) return false;
    pairings[deviceId] = {
      'address': address,
      'pairedAt': DateTime.now().toUtc().toIso8601String(),
    };
    await save();
    return true;
  }

  Future<void> unpair(String deviceId) async {
    pairings.remove(deviceId);
    await save();
  }

  /// `POST /devices` (device.manage) from a scanned advertisement; the new
  /// device is paired with this phone at once.
  Future<Map<String, dynamic>> register(
    HmsClient client, {
    required Advertisement ad,
    required String label,
    required DeviceInfo info,
    String? branchId,
  }) async {
    final created = await client.requestMap('POST', '/devices', body: {
      'kind': ad.kind,
      'label': label,
      'ble_address': ad.address,
      'manufacturer': info.manufacturer,
      'model': info.model,
      'serial': info.serial,
      'firmware': info.firmware,
      'is_simulator': ad.simulated,
      'branch_id': ?branchId,
    });
    devices = [...devices, created];
    pairings['${created['id']}'] = {
      'address': ad.address,
      'pairedAt': DateTime.now().toUtc().toIso8601String(),
    };
    await save();
    return created;
  }
}

/// A measurement parsed for display, before the user saves it.
class CaptureResult {
  CaptureResult(this.measurement, this.reading, this.refusal);
  final Measurement measurement;
  final GattReading reading;

  /// Non-null when the device itself marks the reading unusable: it is
  /// shown, and cannot be saved.
  final String? refusal;
}

CaptureResult parseMeasurement(Measurement m) {
  final reading = parseCharacteristic(m.characteristic, bytesToHex(m.bytes));
  return CaptureResult(m, reading, refusalReason(reading));
}

/// Queue a reviewed-for-display measurement for the API (encrypted outbox,
/// offline-capable). [encounterRef] is the server id, or the `$ref:`
/// placeholder of an encounter created offline — the reading then waits
/// for its encounter. Returns the op (the same op for a repeated save).
OutboxOp queueReading(
  Outbox outbox, {
  required CaptureResult result,
  required Map<String, dynamic> device,
  required String address,
  required String encounterRef,
  required String appVersion,
  String? captureId,
}) {
  if (result.refusal != null) {
    throw StateError('refused readings are never queued');
  }
  final id = captureId ?? Outbox.newId();
  final simulated = device['is_simulator'] == true;
  return outbox.enqueue(
    entity: 'device_reading',
    method: 'POST',
    path: '/device-readings',
    payload: {
      'capture_id': id,
      'device_id': device['id'],
      'ble_address': address,
      'encounter_id': encounterRef,
      'characteristic': result.measurement.characteristic,
      'raw_hex': bytesToHex(result.measurement.bytes),
      'source': simulated ? 'simulator' : 'ble',
      'captured_at': result.measurement.receivedAt.toUtc().toIso8601String(),
      'app_version': appVersion,
      'client_parsed': result.reading.toJson(),
    },
    dedupeKey: 'device_reading:$id',
  );
}

/// True when [ref] still points at an encounter created on this phone.
bool waitsForEncounter(String ref) => ref.startsWith(IdMap.prefix);
