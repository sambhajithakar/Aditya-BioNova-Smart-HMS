/// How the app talks to a measuring device (M8.2).
///
/// Read-only by design: the interface can discover devices, read their
/// identity and RECEIVE a finished measurement. There is no call that
/// writes to a device, starts an inflation or changes a setting.
///
/// Implementations: [SimulatedDeviceTransport] (synthetic readings, M8.2c)
/// and the Bluetooth adapter (M8.2d). Screens and tests depend only on this.
library;

/// Kinds the app supports, matching the API's `medical_devices.kind`.
abstract final class DeviceKinds {
  static const bp = 'bp_monitor';
  static const oximeter = 'pulse_oximeter';
}

/// Bluetooth SIG service UUIDs (16-bit) the scanner filters on.
abstract final class GattServices {
  static const bloodPressure = 0x1810;
  static const pulseOximeter = 0x1822;
  static const deviceInformation = 0x180A;
}

/// A device seen while scanning.
class Advertisement {
  const Advertisement({
    required this.address,
    required this.name,
    required this.kind,
    this.rssi,
    this.simulated = false,
  });

  /// Bluetooth address (or `SIM-…` for the simulator). Not PHI.
  final String address;
  final String name;
  final String kind;
  final int? rssi;
  final bool simulated;
}

/// Device Information service (0x180A) values, when readable.
class DeviceInfo {
  const DeviceInfo({
    this.manufacturer = '',
    this.model = '',
    this.serial = '',
    this.firmware = '',
  });
  final String manufacturer;
  final String model;
  final String serial;
  final String firmware;
}

/// One finished measurement exactly as the device sent it.
class Measurement {
  const Measurement({
    required this.characteristic,
    required this.bytes,
    required this.receivedAt,
  });

  /// '2a35' | '2a5e' | '2a5f'
  final String characteristic;
  final List<int> bytes;
  final DateTime receivedAt;
}

class DeviceException implements Exception {
  DeviceException(this.code, this.message);

  /// permission_denied | bluetooth_off | not_found | timeout | disconnected
  /// | unsupported | cancelled
  final String code;
  final String message;
  @override
  String toString() => message;
}

abstract interface class DeviceTransport {
  /// Nearby devices exposing the Blood Pressure or Pulse Oximeter service.
  Future<List<Advertisement>> scan({Duration timeout});

  /// Device Information (best effort; empty strings when not exposed).
  Future<DeviceInfo> readInfo(String address);

  /// Connect (bonded), wait for ONE finished measurement, disconnect.
  /// [scenario] is honoured by the simulator only.
  Future<Measurement> measure(
    String address, {
    required String kind,
    Duration timeout,
    String? scenario,
  });
}

/// Used when no device stack is available in this build (no Bluetooth
/// adapter wired, simulator off): every call explains why.
class UnavailableDeviceTransport implements DeviceTransport {
  const UnavailableDeviceTransport();

  Never _no() => throw DeviceException(
      'unsupported', 'Device capture is not available in this build');

  @override
  Future<List<Advertisement>> scan({Duration timeout = Duration.zero}) async =>
      _no();

  @override
  Future<DeviceInfo> readInfo(String address) async => _no();

  @override
  Future<Measurement> measure(String address,
          {required String kind,
          Duration timeout = Duration.zero,
          String? scenario}) async =>
      _no();
}

/// What the signed-in user may do with devices (from `/auth/me`). All false
/// unless the server EXPLICITLY reports the `medical_devices` feature and
/// the permission — an older server without the device API shows nothing.
class DeviceAccess {
  const DeviceAccess({
    this.read = false,
    this.manage = false,
    this.capture = false,
    this.review = false,
  });

  static const none = DeviceAccess();

  factory DeviceAccess.from({
    required bool featureReported,
    required Set<String>? permissions,
  }) {
    if (!featureReported || permissions == null) return none;
    return DeviceAccess(
      read: permissions.contains('device.read'),
      manage: permissions.contains('device.manage'),
      capture: permissions.contains('device.capture'),
      // accepting writes vitals: both permissions are required server-side
      review: permissions.contains('device.review') &&
          permissions.contains('encounter.write'),
    );
  }

  final bool read;
  final bool manage;
  final bool capture;
  final bool review;

  bool get any => read || manage || capture || review;
}
