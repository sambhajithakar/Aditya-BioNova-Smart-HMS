// M8.2d: the Bluetooth transport against a FAKE BLE stack (no hardware):
// permissions and adapter state, scan filtering, the live-measurement rule
// (stored backlog ignored), repeated indications, continuous-SpO2 stability,
// unsupported devices, clean disconnects, and the simulator fallback.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:aditya_bionova_mobile/devices/ble_transport.dart';
import 'package:aditya_bionova_mobile/devices/gatt_encode.dart';
import 'package:aditya_bionova_mobile/devices/simulator.dart';
import 'package:aditya_bionova_mobile/devices/transport.dart';
import 'package:flutter_test/flutter_test.dart';

class FakeLink implements BleLink {
  FakeLink(this.chars, this.events);

  final Map<int, Set<int>> chars;

  /// (characteristic, bytes) emitted in order once subscribed
  final List<(int, List<int>)> events;
  final Map<int, List<int>> reads = {};
  bool closed = false;
  final _controllers = <int, StreamController<List<int>>>{};

  @override
  Future<Map<int, Set<int>>> services() async => chars;

  @override
  Future<List<int>> read(int service, int characteristic) async =>
      reads[characteristic] ?? (throw StateError('not readable'));

  @override
  Stream<List<int>> subscribe(int service, int characteristic) {
    final c = _controllers[characteristic] = StreamController<List<int>>();
    // emit everything after all subscriptions are in place
    scheduleMicrotask(() async {
      await Future<void>.delayed(Duration.zero);
      for (final (char, bytes) in events) {
        _controllers[char]?.add(bytes);
        await Future<void>.delayed(Duration.zero);
      }
    });
    return c.stream;
  }

  @override
  Future<void> close() async => closed = true;
}

class FakeBle implements BleApi {
  FakeBle({this.link, this.adverts = const [], this.status = BleState.ready});

  FakeLink? link;
  final List<BleAdvert> adverts;
  BleState status;

  @override
  Future<BleState> state() async => status;

  @override
  Stream<BleAdvert> scan(List<int> services) => Stream.fromIterable(adverts);

  @override
  Future<BleLink> connect(String address, Duration timeout) async => link!;
}

BleDeviceTransport transport(FakeBle api, {String permission = 'granted', DateTime? now}) =>
    BleDeviceTransport(
        api: api,
        requestPermission: () async => permission,
        clock: () => now ?? DateTime(2026, 10, 21, 10, 0));

final bpChars = {
  svcBloodPressure: {chrBpMeasurement, chrCuffPressure},
};

void main() {
  test('permission and adapter state are checked first', () async {
    expect(() => transport(FakeBle(), permission: 'denied').scan(),
        throwsA(isA<DeviceException>().having((e) => e.code, 'code', 'permission_denied')));
    expect(
        () => transport(FakeBle(), permission: 'permanently_denied').scan(),
        throwsA(isA<DeviceException>()
            .having((e) => e.message, 'message', contains('Android settings'))));
    expect(() => transport(FakeBle(status: BleState.poweredOff)).scan(),
        throwsA(isA<DeviceException>().having((e) => e.code, 'code', 'bluetooth_off')));
  });

  test('scan keeps only BP / pulse-oximeter devices, once each', () async {
    final api = FakeBle(adverts: const [
      BleAdvert('aa:bb:cc:dd:ee:01', 'BP-X', {svcBloodPressure}, -50),
      BleAdvert('AA:BB:CC:DD:EE:01', 'BP-X', {svcBloodPressure}, -48),
      BleAdvert('aa:bb:cc:dd:ee:02', '', {svcPulseOximeter}, -60),
      BleAdvert('aa:bb:cc:dd:ee:03', 'Thermometer', {0x1809}, -40),
    ]);
    final found = await transport(api).scan(timeout: const Duration(milliseconds: 20));
    expect([for (final a in found) (a.address, a.kind)], [
      ('AA:BB:CC:DD:EE:01', DeviceKinds.bp),
      ('AA:BB:CC:DD:EE:02', DeviceKinds.oximeter),
    ]);
  });

  test('a BP monitor replaying its memory: only the live measurement is taken',
      () async {
    final now = DateTime(2026, 10, 21, 10, 0);
    List<int> bp(int sys, DateTime t) =>
        encodeBloodPressure(systolic: sys, diastolic: 80, mean: 95, deviceClock: t);
    final link = FakeLink(bpChars, [
      (chrBpMeasurement, bp(150, DateTime(2026, 10, 19, 8, 0))), // stored
      (chrBpMeasurement, bp(145, DateTime(2026, 10, 20, 8, 0))), // stored
      (chrBpMeasurement, bp(145, DateTime(2026, 10, 20, 8, 0))), // repeat
      (chrBpMeasurement, bp(128, now.subtract(const Duration(minutes: 1)))), // live
    ]);
    final t = transport(FakeBle(link: link), now: now);
    final m = await t.measure('AA:BB:CC:DD:EE:01', kind: DeviceKinds.bp);
    expect(m.characteristic, '2a35');
    expect(m.bytes, bp(128, now.subtract(const Duration(minutes: 1))));
    expect(t.lastSkipped, 2);
    expect(link.closed, isTrue);
  });

  test('BP without a time stamp counts only after a live cuff inflation', () async {
    final noTime = encodeBloodPressure(systolic: 132, diastolic: 84, mean: 100);
    final later = encodeBloodPressure(systolic: 118, diastolic: 76, mean: 90);
    final link = FakeLink(bpChars, [
      (chrBpMeasurement, noTime), // replayed before any inflation: ignored
      (chrCuffPressure, [0x00, ...sfloatBytes(60), 0xFF, 0x07, 0xFF, 0x07]),
      (chrBpMeasurement, later),
    ]);
    final m = await transport(FakeBle(link: link))
        .measure('AA:BB:CC:DD:EE:01', kind: DeviceKinds.bp);
    expect(m.bytes, later);
  });

  test('no live measurement: a timeout that says how many were ignored', () async {
    final link = FakeLink(bpChars, [
      (chrBpMeasurement,
          encodeBloodPressure(systolic: 150, diastolic: 90, mean: 110,
              deviceClock: DateTime(2025, 1, 1))),
    ]);
    final t = transport(FakeBle(link: link));
    await expectLater(
        t.measure('AA:BB:CC:DD:EE:01',
            kind: DeviceKinds.bp, timeout: const Duration(milliseconds: 100)),
        throwsA(isA<DeviceException>()
            .having((e) => e.code, 'code', 'timeout')
            .having((e) => e.message, 'message', contains('1 stored or old'))));
    expect(link.closed, isTrue);
  });

  test('continuous SpO2 is captured only once stable', () async {
    List<int> cont(int spo2, int pulse, {int status = -1}) => [
          status >= 0 ? 0x04 : 0x00,
          ...sfloatBytes(spo2),
          ...sfloatBytes(pulse),
          if (status >= 0) ...[status & 0xFF, status >> 8],
        ];
    final link = FakeLink({
      svcPulseOximeter: {chrPlxContinuous},
    }, [
      (chrPlxContinuous, cont(91, 80)),
      (chrPlxContinuous, cont(95, 78)),
      (chrPlxContinuous, cont(97, 75, status: 1 << 5)), // measurement ongoing
      for (var i = 0; i < 5; i++) (chrPlxContinuous, cont(97, 74 + (i % 2))),
    ]);
    final m = await transport(FakeBle(link: link))
        .measure('AA:BB:CC:DD:EE:02', kind: DeviceKinds.oximeter);
    expect(m.characteristic, '2a5f');
    expect(m.bytes, cont(97, 74 + (4 % 2)));
  });

  test('stored spot-checks are skipped; malformed notifications ignored', () async {
    final link = FakeLink({
      svcPulseOximeter: {chrPlxSpotCheck},
    }, [
      (chrPlxSpotCheck, encodePlxSpotCheck(spo2: 93, pulse: 88, measurementStatus: 1 << 9)),
      (chrPlxSpotCheck, [0x00, 0x01]), // truncated
      (chrPlxSpotCheck, encodePlxSpotCheck(spo2: 98, pulse: 70)),
    ]);
    final m = await transport(FakeBle(link: link))
        .measure('AA:BB:CC:DD:EE:02', kind: DeviceKinds.oximeter);
    expect(m.bytes, encodePlxSpotCheck(spo2: 98, pulse: 70));
  });

  test('a device without the standard characteristic is refused', () async {
    final link = FakeLink({
      svcBloodPressure: {0x2A49},
    }, const []);
    await expectLater(
        transport(FakeBle(link: link)).measure('A', kind: DeviceKinds.bp),
        throwsA(isA<DeviceException>().having((e) => e.code, 'code', 'unsupported')));
    expect(link.closed, isTrue);
  });

  test('Device Information is read and trimmed', () async {
    final link = FakeLink({
      svcDeviceInfo: {chrManufacturer, chrModel, chrFirmware},
    }, const [])
      ..reads[chrManufacturer] = utf8.encode('Example Medical\u0000')
      ..reads[chrModel] = utf8.encode(' BP-100 ')
      ..reads[chrFirmware] = utf8.encode('1.2.3');
    final info = await transport(FakeBle(link: link)).readInfo('A');
    expect((info.manufacturer, info.model, info.serial, info.firmware),
        ('Example Medical', 'BP-100', '', '1.2.3'));
    expect(link.closed, isTrue);
  });

  test('composite: SIM- addresses use the simulator; no Bluetooth still lists it',
      () async {
    final composite = CompositeDeviceTransport(
        transport(FakeBle(status: BleState.poweredOff)), SimulatedDeviceTransport());
    final found = await composite.scan(timeout: const Duration(milliseconds: 10));
    expect(found.every((a) => a.simulated), isTrue);
    final m = await composite.measure('SIM-0000B001', kind: DeviceKinds.bp);
    expect(m.characteristic, '2a35');
    final bleOnly = CompositeDeviceTransport(
        transport(FakeBle(status: BleState.poweredOff)), null);
    expect(() => bleOnly.scan(timeout: Duration.zero), throwsA(isA<DeviceException>()));
  });

  test('uuid helpers', () {
    expect(short16('1810'), 0x1810);
    expect(short16('00002a35-0000-1000-8000-00805f9b34fb'), 0x2A35);
    expect(short16('6e400001-b5a3-f393-e0a9-e50e24dcca9e'), isNull);
    expect(hex16(0x2A5E), '2a5e');
  });

  test('manifest: Bluetooth permissions are scoped; no foreground service', () {
    final m = File('android/app/src/main/AndroidManifest.xml').readAsStringSync();
    expect(m, contains('android.permission.BLUETOOTH_SCAN'));
    expect(m, contains('android:usesPermissionFlags="neverForLocation"'));
    expect(m, contains('android.permission.BLUETOOTH_CONNECT'));
    expect(
        RegExp(r'ACCESS_FINE_LOCATION"\s+android:maxSdkVersion="30"').hasMatch(m), isTrue);
    expect(m, contains('android:name="android.hardware.bluetooth_le" android:required="false"'));
    // the plugin's unbounded location request is stripped from the merge
    expect(m, contains('<uses-permission-sdk-23 android:name="android.permission.ACCESS_FINE_LOCATION"\n        tools:node="remove" />'));
    expect(m, contains('android:name="android.hardware.bluetooth" android:required="false"'));
    expect(m, isNot(contains('FOREGROUND_SERVICE')));
    expect(m, isNot(contains('ACCESS_BACKGROUND_LOCATION')));
  });
}
