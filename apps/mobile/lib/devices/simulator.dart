/// In-app device simulator (M8.2c): two virtual blood-pressure monitors and
/// two virtual pulse oximeters with fixed `SIM-…` addresses, producing
/// SYNTHETIC, specification-shaped payloads through the same
/// [DeviceTransport] interface as real Bluetooth.
///
/// The API accepts simulated readings only where `DEVICE_SIMULATOR_ENABLED`
/// is on (development/test; production refuses to start with it), and the
/// app labels every simulated reading "SIMULATED".
library;

import 'gatt_encode.dart';
import 'transport.dart';

/// On in debug/profile builds and in the demo APK (CI passes
/// `--dart-define=HMS_DEVICE_SIMULATOR=true`); off in other release builds.
const bool kDeviceSimulator = bool.fromEnvironment('HMS_DEVICE_SIMULATOR',
    defaultValue: !bool.fromEnvironment('dart.vm.product'));

class SimScenario {
  const SimScenario(this.key, this.kind, this.label);
  final String key;
  final String kind;
  final String label; // English description shown in the picker
}

const simScenarios = <SimScenario>[
  SimScenario('bp_normal', DeviceKinds.bp, 'BP 122/78, pulse 72'),
  SimScenario('bp_high_irregular', DeviceKinds.bp,
      'BP 168/102, pulse 96, irregular pulse + movement'),
  SimScenario('bp_no_clock', DeviceKinds.bp, 'BP 118/76, device clock not set'),
  SimScenario('spo2_normal', DeviceKinds.oximeter, 'SpO2 98 %, pulse 70'),
  SimScenario('spo2_low', DeviceKinds.oximeter, 'SpO2 86 %, pulse 112 (low)'),
  SimScenario('spo2_from_storage', DeviceKinds.oximeter,
      'Stored record from device memory (must be refused)'),
  SimScenario('spo2_invalid', DeviceKinds.oximeter,
      'Device marks the measurement invalid (must be refused)'),
];

const simulatedDevices = <Advertisement>[
  Advertisement(
      address: 'SIM-0000B001',
      name: 'Simulated BP monitor 1',
      kind: DeviceKinds.bp,
      simulated: true),
  Advertisement(
      address: 'SIM-0000B002',
      name: 'Simulated BP monitor 2',
      kind: DeviceKinds.bp,
      simulated: true),
  Advertisement(
      address: 'SIM-0000A001',
      name: 'Simulated pulse oximeter 1',
      kind: DeviceKinds.oximeter,
      simulated: true),
  Advertisement(
      address: 'SIM-0000A002',
      name: 'Simulated pulse oximeter 2',
      kind: DeviceKinds.oximeter,
      simulated: true),
];

class SimulatedDeviceTransport implements DeviceTransport {
  SimulatedDeviceTransport({DateTime Function()? clock})
      : _clock = clock ?? DateTime.now;

  final DateTime Function() _clock;

  static bool isSimAddress(String address) =>
      address.toUpperCase().startsWith('SIM-');

  @override
  Future<List<Advertisement>> scan(
          {Duration timeout = const Duration(seconds: 8)}) async =>
      simulatedDevices;

  @override
  Future<DeviceInfo> readInfo(String address) async {
    _find(address);
    return DeviceInfo(
      manufacturer: 'Aditya BioNova (simulator)',
      model: 'SIM-1',
      serial: address.toUpperCase(),
      firmware: 'sim-1.0',
    );
  }

  Advertisement _find(String address) => simulatedDevices.firstWhere(
        (d) => d.address == address.toUpperCase(),
        orElse: () =>
            throw DeviceException('not_found', 'Simulated device not found'),
      );

  @override
  Future<Measurement> measure(
    String address, {
    required String kind,
    Duration timeout = const Duration(seconds: 90),
    String? scenario,
  }) async {
    final device = _find(address);
    if (device.kind != kind) {
      throw DeviceException('unsupported', 'Wrong device type');
    }
    final now = _clock();
    final local = now.toLocal();
    final key = scenario ??
        (kind == DeviceKinds.bp ? 'bp_normal' : 'spo2_normal');
    final (String char, List<int> bytes) = switch (key) {
      'bp_normal' => ('2a35', encodeBloodPressure(
          systolic: 122, diastolic: 78, mean: 93, pulse: 72,
          deviceClock: local, status: 0)),
      'bp_high_irregular' => ('2a35', encodeBloodPressure(
          systolic: 168, diastolic: 102, mean: 124, pulse: 96,
          deviceClock: local, status: 0x0005)),
      // time stamp present but all zero: "device does not know the date"
      'bp_no_clock' => ('2a35', [
          0x06, ...sfloatBytes(118), ...sfloatBytes(76), ...sfloatBytes(90),
          0, 0, 0, 0, 0, 0, 0, ...sfloatBytes(70),
        ]),
      'spo2_normal' => ('2a5e', encodePlxSpotCheck(
          spo2: 98, pulse: 70, deviceClock: local, measurementStatus: 1 << 7)),
      'spo2_low' => ('2a5e', encodePlxSpotCheck(
          spo2: 86, pulse: 112, deviceClock: local,
          measurementStatus: 1 << 7)),
      'spo2_from_storage' => ('2a5e', encodePlxSpotCheck(
          spo2: 95, pulse: 80, measurementStatus: 1 << 9)),
      'spo2_invalid' => ('2a5e', encodePlxSpotCheck(
          spo2: 97, pulse: 70, measurementStatus: 1 << 15)),
      _ => throw DeviceException('unsupported', 'Unknown scenario $key'),
    };
    return Measurement(characteristic: char, bytes: bytes, receivedAt: now);
  }
}
