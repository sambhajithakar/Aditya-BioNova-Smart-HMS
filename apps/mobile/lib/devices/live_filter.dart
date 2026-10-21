/// Which notifications are a LIVE measurement of the patient in front of the
/// clinician (M8.2d).
///
/// Many Bluetooth BP monitors replay their stored memory as indications as
/// soon as a phone connects. Attaching such an old value to today's patient
/// would be a wrong-patient error, so a measurement is accepted only when:
///   * the device does not mark it as stored (PLX "from device storage"), and
///   * its own time stamp is within [window] of the phone's clock, or
///   * it has no usable time stamp, and — for a BP monitor — intermediate cuff
///     pressure was seen on THIS connection (a live inflation happened).
/// Everything else is skipped (and counted, so the screen can say so).
///
/// For continuous oximetry (0x2A5F) a value is captured only once it is
/// stable: [StabilityTracker].
library;

import 'gatt.dart';

enum LiveVerdict { live, stored, unusable }

class LiveFilter {
  LiveFilter({this.window = const Duration(minutes: 10)});

  final Duration window;
  bool _cuffSeen = false;
  int skipped = 0;
  final Set<String> _seen = {};

  /// Intermediate Cuff Pressure (0x2A36) arrived: an inflation is happening.
  void cuffPressureSeen() => _cuffSeen = true;

  /// Same bytes twice on one connection (repeated indication): ignored.
  bool isRepeat(List<int> bytes) => !_seen.add(bytesToHex(bytes));

  LiveVerdict consider(GattReading r, DateTime receivedAt) {
    if (r.flags.contains('from_device_storage')) return _skip(LiveVerdict.stored);
    final t = r.deviceTime;
    if (t != null && !r.flags.contains('device_clock_not_set')) {
      // the device reports local wall-clock time without a zone
      final device = DateTime.parse(t);
      final phone = receivedAt.toLocal();
      final local = DateTime(phone.year, phone.month, phone.day, phone.hour,
          phone.minute, phone.second);
      return device.difference(local).abs() <= window
          ? LiveVerdict.live
          : _skip(LiveVerdict.stored);
    }
    if (r.kind == 'blood_pressure') {
      return _cuffSeen ? LiveVerdict.live : _skip(LiveVerdict.stored);
    }
    return LiveVerdict.live;
  }

  LiveVerdict _skip(LiveVerdict v) {
    skipped += 1;
    return v;
  }
}

/// Continuous SpO2: capture when [needed] consecutive usable samples agree
/// (SpO2 identical, pulse within ±[pulseTolerance] bpm).
class StabilityTracker {
  StabilityTracker({this.needed = 5, this.pulseTolerance = 2});

  final int needed;
  final int pulseTolerance;
  final List<GattReading> _run = [];

  /// Returns the reading to capture, or null while still settling.
  GattReading? add(GattReading r) {
    if (refusalReason(r) != null) {
      _run.clear();
      return null;
    }
    if (_run.isNotEmpty) {
      final first = _run.first.values;
      final same = r.values['spo2'] == first['spo2'] &&
          ((r.values['pulse'] ?? 0) - (first['pulse'] ?? 0)).abs() <=
              pulseTolerance;
      if (!same) _run.clear();
    }
    _run.add(r);
    return _run.length >= needed ? r : null;
  }
}
