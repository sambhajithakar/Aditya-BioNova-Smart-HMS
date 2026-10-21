/// Bluetooth Low Energy device transport (M8.2d) on `flutter_reactive_ble`
/// (BSD-3-Clause; see LICENSES.md).
///
/// READ-ONLY: scans for the Blood Pressure (0x1810) and Pulse Oximeter
/// (0x1822) services, reads Device Information (0x180A) and subscribes to
/// the measurement characteristics. It never writes a characteristic, never
/// uses the Record Access Control Point (stored records) and never starts a
/// measurement — the clinician operates the device as usual.
///
/// Bonding: devices that require an encrypted link (the PLX profile does)
/// make Android show its own pairing dialog when the app first reads or
/// subscribes; the plugin exposes no bonding API, so "bonded" is not
/// asserted by the app.
///
/// NOT VALIDATED ON HARDWARE. This code compiles and is unit-tested against
/// a fake BLE stack only (test/ble_transport_test.dart). No device model is
/// supported until it passes the protocol in docs/DEVICE_SUPPORT.md.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_reactive_ble/flutter_reactive_ble.dart' as rb;

import 'gatt.dart';
import 'live_filter.dart';
import 'simulator.dart';
import 'transport.dart';

// --- 16-bit GATT numbers ------------------------------------------------------
const int svcBloodPressure = 0x1810;
const int svcPulseOximeter = 0x1822;
const int svcDeviceInfo = 0x180A;
const int chrBpMeasurement = 0x2A35;
const int chrCuffPressure = 0x2A36;
const int chrPlxSpotCheck = 0x2A5E;
const int chrPlxContinuous = 0x2A5F;
const int chrManufacturer = 0x2A29;
const int chrModel = 0x2A24;
const int chrSerial = 0x2A25;
const int chrFirmware = 0x2A26;

String hex16(int v) => v.toRadixString(16).padLeft(4, '0');

/// 16-bit value of a Bluetooth SIG UUID string (short or base-UUID form).
int? short16(String uuid) {
  final s = uuid.toLowerCase();
  if (RegExp(r'^[0-9a-f]{4}$').hasMatch(s)) return int.parse(s, radix: 16);
  final m = RegExp(r'^0000([0-9a-f]{4})-0000-1000-8000-00805f9b34fb$').firstMatch(s);
  return m == null ? null : int.parse(m.group(1)!, radix: 16);
}

// --- facade (the plugin in production, a fake in tests) -------------------------
enum BleState { ready, poweredOff, unauthorized, unsupported, locationOff, unknown }

class BleAdvert {
  const BleAdvert(this.address, this.name, this.services, this.rssi);
  final String address;
  final String name;
  final Set<int> services;
  final int rssi;
}

abstract interface class BleLink {
  /// service -> characteristic numbers discovered on this connection
  Future<Map<int, Set<int>>> services();
  Future<List<int>> read(int service, int characteristic);
  Stream<List<int>> subscribe(int service, int characteristic);
  Future<void> close();
}

abstract interface class BleApi {
  Future<BleState> state();
  Stream<BleAdvert> scan(List<int> services);
  Future<BleLink> connect(String address, Duration timeout);
}

/// Runtime permission request (MainActivity's channel).
typedef PermissionRequest = Future<String> Function();

const _permissions = MethodChannel('com.adityabionova.smarthms/ble_permissions');

Future<String> requestBlePermissions() async =>
    await _permissions.invokeMethod<String>('request') ?? 'denied';

// --- transport ---------------------------------------------------------------------
class BleDeviceTransport implements DeviceTransport {
  BleDeviceTransport({
    required this.api,
    PermissionRequest? requestPermission,
    DateTime Function()? clock,
  })  : _request = requestPermission ?? requestBlePermissions,
        _clock = clock ?? DateTime.now;

  final BleApi api;
  final PermissionRequest _request;
  final DateTime Function() _clock;

  /// Notifications skipped as stored / repeated during the last [measure].
  int lastSkipped = 0;

  Future<void> _ready() async {
    final granted = await _request();
    if (granted != 'granted') {
      throw DeviceException('permission_denied',
          granted == 'permanently_denied'
              ? 'Bluetooth permission is off for this app; allow it in Android settings'
              : 'Bluetooth permission is needed to use medical devices');
    }
    switch (await api.state()) {
      case BleState.ready:
        return;
      case BleState.poweredOff:
        throw DeviceException('bluetooth_off', 'Turn Bluetooth on');
      case BleState.locationOff:
        throw DeviceException('bluetooth_off',
            'Turn on Location: Android 11 and older need it for Bluetooth scans');
      case BleState.unauthorized:
        throw DeviceException('permission_denied', 'Bluetooth is not allowed');
      case BleState.unsupported:
        throw DeviceException('unsupported', 'This phone has no Bluetooth LE');
      case BleState.unknown:
        throw DeviceException('bluetooth_off', 'Bluetooth is not ready yet; try again');
    }
  }

  @override
  Future<List<Advertisement>> scan(
      {Duration timeout = const Duration(seconds: 8)}) async {
    await _ready();
    final found = <String, Advertisement>{};
    final sub = api.scan(const [svcBloodPressure, svcPulseOximeter]).listen((a) {
      final kind = a.services.contains(svcBloodPressure)
          ? DeviceKinds.bp
          : a.services.contains(svcPulseOximeter)
              ? DeviceKinds.oximeter
              : null;
      if (kind == null) return;
      found[a.address.toUpperCase()] = Advertisement(
          address: a.address.toUpperCase(),
          name: a.name.isEmpty ? a.address : a.name,
          kind: kind,
          rssi: a.rssi);
    });
    await Future<void>.delayed(timeout);
    await sub.cancel();
    return found.values.toList();
  }

  @override
  Future<DeviceInfo> readInfo(String address) async {
    await _ready();
    final link = await api.connect(address, const Duration(seconds: 15));
    try {
      final chars = (await link.services())[svcDeviceInfo] ?? const <int>{};
      Future<String> text(int c) async {
        if (!chars.contains(c)) return '';
        try {
          final v = utf8.decode(await link.read(svcDeviceInfo, c), allowMalformed: true);
          return v.replaceAll('\u0000', '').trim();
        } catch (_) {
          return '';
        }
      }

      String cut(String v, int n) => v.length > n ? v.substring(0, n) : v;
      return DeviceInfo(
        manufacturer: cut(await text(chrManufacturer), 80),
        model: cut(await text(chrModel), 80),
        serial: cut(await text(chrSerial), 80),
        firmware: cut(await text(chrFirmware), 40),
      );
    } finally {
      await link.close();
    }
  }

  @override
  Future<Measurement> measure(
    String address, {
    required String kind,
    Duration timeout = const Duration(seconds: 120),
    String? scenario,
  }) async {
    await _ready();
    final link = await api.connect(address, const Duration(seconds: 15));
    final subs = <StreamSubscription<List<int>>>[];
    final done = Completer<Measurement>();
    final filter = LiveFilter();
    final stable = StabilityTracker();
    lastSkipped = 0;

    void fail(Object e) {
      if (!done.isCompleted) done.completeError(e);
    }

    void offer(String char, List<int> bytes, {bool continuous = false}) {
      if (done.isCompleted) return;
      // a repeated indication of one measurement is dropped; identical
      // continuous samples are expected (that is what "stable" means)
      if (!continuous && filter.isRepeat(bytes)) return;
      final GattReading reading;
      try {
        reading = parseCharacteristic(char, bytesToHex(bytes));
      } on GattError {
        lastSkipped += 1; // malformed notification: never shown or kept
        return;
      }
      final now = _clock();
      if (continuous) {
        if (stable.add(reading) == null) return;
      } else if (filter.consider(reading, now) != LiveVerdict.live) {
        lastSkipped = filter.skipped;
        return;
      }
      done.complete(Measurement(characteristic: char, bytes: bytes, receivedAt: now));
    }

    try {
      final services = await link.services();
      if (kind == DeviceKinds.bp) {
        final chars = services[svcBloodPressure] ?? const <int>{};
        if (!chars.contains(chrBpMeasurement)) {
          throw DeviceException('unsupported',
              'This device does not expose the standard Blood Pressure Measurement');
        }
        if (chars.contains(chrCuffPressure)) {
          subs.add(link.subscribe(svcBloodPressure, chrCuffPressure).listen(
              (_) => filter.cuffPressureSeen(),
              onError: (_) {}));
        }
        subs.add(link
            .subscribe(svcBloodPressure, chrBpMeasurement)
            .listen((b) => offer('2a35', b), onError: fail));
      } else {
        final chars = services[svcPulseOximeter] ?? const <int>{};
        if (chars.contains(chrPlxSpotCheck)) {
          subs.add(link
              .subscribe(svcPulseOximeter, chrPlxSpotCheck)
              .listen((b) => offer('2a5e', b), onError: fail));
        }
        if (chars.contains(chrPlxContinuous)) {
          subs.add(link.subscribe(svcPulseOximeter, chrPlxContinuous).listen(
              (b) => offer('2a5f', b, continuous: true),
              onError: fail));
        }
        if (subs.isEmpty) {
          throw DeviceException('unsupported',
              'This device does not expose the standard Pulse Oximeter measurements');
        }
      }
      return await done.future.timeout(timeout,
          onTimeout: () => throw DeviceException(
              'timeout',
              lastSkipped > 0
                  ? 'No live measurement received ($lastSkipped stored or old '
                      'readings were ignored). Measure again.'
                  : 'No measurement received. Take the measurement on the device.'));
    } finally {
      for (final s in subs) {
        await s.cancel();
      }
      await link.close();
    }
  }
}

/// Bluetooth plus, when compiled in, the simulator (addresses `SIM-…`).
class CompositeDeviceTransport implements DeviceTransport {
  CompositeDeviceTransport(this.ble, this.simulator);

  final DeviceTransport ble;
  final DeviceTransport? simulator;

  DeviceTransport _for(String address) =>
      SimulatedDeviceTransport.isSimAddress(address) && simulator != null
          ? simulator!
          : ble;

  @override
  Future<List<Advertisement>> scan(
      {Duration timeout = const Duration(seconds: 8)}) async {
    final sim = simulator == null ? const <Advertisement>[] : await simulator!.scan();
    try {
      return [...await ble.scan(timeout: timeout), ...sim];
    } on DeviceException {
      // no Bluetooth / no permission: the simulator still works
      if (sim.isNotEmpty) return sim;
      rethrow;
    }
  }

  @override
  Future<DeviceInfo> readInfo(String address) => _for(address).readInfo(address);

  @override
  Future<Measurement> measure(String address,
          {required String kind,
          Duration timeout = const Duration(seconds: 120),
          String? scenario}) =>
      _for(address).measure(address, kind: kind, timeout: timeout, scenario: scenario);
}

// --- production facade over flutter_reactive_ble ---------------------------------
class ReactiveBleApi implements BleApi {
  ReactiveBleApi([this._override]);

  final rb.FlutterReactiveBle? _override;

  // created on first use: no platform channel is touched until the user
  // opens device pairing or capture
  late final rb.FlutterReactiveBle _ble = _override ?? rb.FlutterReactiveBle();

  @override
  Future<BleState> state() async {
    final s = await _ble.statusStream
        .firstWhere((s) => s != rb.BleStatus.unknown)
        .timeout(const Duration(seconds: 3), onTimeout: () => rb.BleStatus.unknown);
    return switch (s) {
      rb.BleStatus.ready => BleState.ready,
      rb.BleStatus.poweredOff => BleState.poweredOff,
      rb.BleStatus.unauthorized => BleState.unauthorized,
      rb.BleStatus.unsupported => BleState.unsupported,
      rb.BleStatus.locationServicesDisabled => BleState.locationOff,
      rb.BleStatus.unknown => BleState.unknown,
    };
  }

  @override
  Stream<BleAdvert> scan(List<int> services) => _ble
      .scanForDevices(
          withServices: [for (final s in services) rb.Uuid.parse(hex16(s))],
          scanMode: rb.ScanMode.lowLatency)
      .map((d) => BleAdvert(
          d.id,
          d.name,
          {for (final u in d.serviceUuids) ?short16(u.toString())},
          d.rssi));

  @override
  Future<BleLink> connect(String address, Duration timeout) async {
    final connected = Completer<void>();
    final sub = _ble.connectToDevice(id: address, connectionTimeout: timeout).listen(
      (u) {
        if (u.connectionState == rb.DeviceConnectionState.connected &&
            !connected.isCompleted) {
          connected.complete();
        } else if (u.connectionState == rb.DeviceConnectionState.disconnected &&
            !connected.isCompleted) {
          connected.completeError(
              DeviceException('disconnected', 'The device disconnected'));
        }
      },
      onError: (Object e) {
        if (!connected.isCompleted) {
          connected.completeError(e is TimeoutException
              ? DeviceException('timeout', 'The device did not answer; is it on and nearby?')
              : DeviceException('disconnected', 'Could not connect: $e'));
        }
      },
    );
    try {
      await connected.future;
    } catch (_) {
      await sub.cancel();
      rethrow;
    }
    return _ReactiveLink(_ble, address, sub);
  }
}

class _ReactiveLink implements BleLink {
  _ReactiveLink(this._ble, this._address, this._connection);

  final rb.FlutterReactiveBle _ble;
  final String _address;
  final StreamSubscription<rb.ConnectionStateUpdate> _connection;

  rb.QualifiedCharacteristic _q(int service, int characteristic) =>
      rb.QualifiedCharacteristic(
          serviceId: rb.Uuid.parse(hex16(service)),
          characteristicId: rb.Uuid.parse(hex16(characteristic)),
          deviceId: _address);

  @override
  Future<Map<int, Set<int>>> services() async {
    final out = <int, Set<int>>{};
    for (final s in await _ble.getDiscoveredServices(_address)) {
      final id = short16(s.id.toString());
      if (id == null) continue;
      out[id] = {
        for (final c in s.characteristics) ?short16(c.id.toString()),
      };
    }
    return out;
  }

  @override
  Future<List<int>> read(int service, int characteristic) =>
      _ble.readCharacteristic(_q(service, characteristic));

  @override
  Stream<List<int>> subscribe(int service, int characteristic) =>
      _ble.subscribeToCharacteristic(_q(service, characteristic));

  @override
  Future<void> close() => _connection.cancel(); // cancelling disconnects
}

/// The transport the app uses: Bluetooth, plus the simulator when compiled in.
DeviceTransport defaultDeviceTransport() => CompositeDeviceTransport(
    BleDeviceTransport(api: ReactiveBleApi()),
    kDeviceSimulator ? SimulatedDeviceTransport() : null);
