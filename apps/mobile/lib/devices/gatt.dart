/// Parsers for the standard Bluetooth SIG health characteristics (M8.2).
///
/// Line-for-line equivalent of the API's `app/devices/gatt.py`; both are
/// checked against the SYNTHETIC vectors in
/// `packages/contracts/device_vectors.json`. The app parses only to show the
/// clinician what was measured — the API parses the raw bytes again and
/// stores its own result.
///
/// Implemented from the Blood Pressure Service and Pulse Oximeter Service
/// specifications; no vendor code. Agreement with real devices is shown only
/// by hardware validation (docs/DEVICE_SUPPORT.md).
library;

const double kpaToMmhg = 7.50062;

class GattError implements Exception {
  GattError(this.message);
  final String message;
  @override
  String toString() => message;
}

const Map<int, String> _special = {
  0x07FF: 'NaN',
  0x0800: 'NRes',
  0x07FE: '+INF',
  0x0802: '-INF',
  0x0801: 'reserved',
};

/// (mantissa, exponent) of an IEEE 11073 16-bit SFLOAT.
(int, int) sfloat(int raw) {
  final s = _special[raw];
  if (s != null) throw GattError('device reported $s instead of a value');
  var mantissa = raw & 0x0FFF;
  if (mantissa >= 0x0800) mantissa -= 0x1000;
  var exponent = raw >> 12;
  if (exponent >= 0x8) exponent -= 0x10;
  return (mantissa, exponent);
}

int _pow10(int n) {
  var v = 1;
  for (var i = 0; i < n; i++) {
    v *= 10;
  }
  return v;
}

double asDouble((int, int) v) {
  final (m, e) = v;
  return e >= 0 ? (m * _pow10(e)).toDouble() : m / _pow10(-e);
}

/// Exact decimal text of mantissa × 10^exponent.
String asDecimal((int, int) v) {
  final (m, e) = v;
  if (e >= 0) return '${m * _pow10(e)}';
  final sign = m < 0 ? '-' : '';
  final digits = '${m.abs()}'.padLeft(-e + 1, '0');
  final cut = digits.length + e;
  return '$sign${digits.substring(0, cut)}.${digits.substring(cut)}';
}

/// Nearest integer, halves away from zero (same as the API).
int halfUp(double v) => v >= 0 ? (v + 0.5).floor() : -((-v + 0.5).floor());

class _Reader {
  _Reader(this.data);
  final List<int> data;
  int pos = 0;

  List<int> take(int n) {
    if (pos + n > data.length) {
      throw GattError('payload is shorter than its flags announce');
    }
    final out = data.sublist(pos, pos + n);
    pos += n;
    return out;
  }

  int u8() => take(1)[0];
  int u16() {
    final b = take(2);
    return b[0] | (b[1] << 8);
  }

  int u24() {
    final b = take(3);
    return b[0] | (b[1] << 8) | (b[2] << 16);
  }

  (int, int) sf() => sfloat(u16());

  /// Date Time (0x2A08): (iso, known).
  (String?, bool) dateTime() {
    final year = u16();
    final b = take(5);
    final (month, day, hh, mm, ss) = (b[0], b[1], b[2], b[3], b[4]);
    if (year == 0 || month == 0 || day == 0) return (null, false);
    if (!(year >= 1582 && year <= 9999 && month <= 12 && day <= 31 &&
        hh < 24 && mm < 60 && ss < 60)) {
      throw GattError('device time stamp is out of range');
    }
    String p2(int v) => v.toString().padLeft(2, '0');
    return ('${year.toString().padLeft(4, '0')}-${p2(month)}-${p2(day)}'
        'T${p2(hh)}:${p2(mm)}:${p2(ss)}', true);
  }

  void done() {
    if (pos != data.length) {
      throw GattError('payload is longer than its flags announce');
    }
  }
}

List<String> _bits(int value, Map<int, String> names) => [
      for (final e in names.entries)
        if (value & (1 << e.key) != 0) e.value,
    ];

/// The normalised result, identical in shape to the API's dict.
class GattReading {
  GattReading({
    required this.kind,
    required this.characteristic,
    required this.values,
    required this.exact,
    required this.unit,
    required this.deviceTime,
    required this.userId,
    required List<String> flags,
  }) : flags = (flags.toSet().toList()..sort());

  final String kind; // blood_pressure | spo2
  final String characteristic;
  final Map<String, int> values;
  final Map<String, String> exact;
  final String unit;
  final String? deviceTime;
  final int? userId;
  final List<String> flags;

  Map<String, Object?> toJson() => {
        'kind': kind,
        'characteristic': characteristic,
        'values': values,
        'exact': exact,
        'unit': unit,
        'device_time': deviceTime,
        'user_id': userId,
        'flags': flags,
      };
}

const Map<int, String> _bpStatus = {
  0: 'body_movement',
  1: 'cuff_too_loose',
  2: 'irregular_pulse',
  5: 'improper_position',
};
const Map<int, String> _bpPulseRange = {
  1: 'pulse_above_range',
  2: 'pulse_below_range',
};

GattReading parseBloodPressure(List<int> data) {
  final r = _Reader(data);
  final flags = r.u8();
  if (flags & 0xE0 != 0) throw GattError('reserved flag bits are set');
  final kpa = flags & 0x01 != 0;
  final sys = r.sf(), dia = r.sf(), mean = r.sf();
  String? deviceTime;
  final out = <String>[];
  if (flags & 0x02 != 0) {
    final (iso, known) = r.dateTime();
    deviceTime = iso;
    if (!known) out.add('device_clock_not_set');
  }
  final pulse = flags & 0x04 != 0 ? r.sf() : null;
  int? userId = flags & 0x08 != 0 ? r.u8() : null;
  if (flags & 0x10 != 0) {
    final status = r.u16();
    out.addAll(_bits(status, _bpStatus));
    final range = _bpPulseRange[(status >> 3) & 0x3];
    if (range != null) out.add(range);
  }
  r.done();
  int mmhg((int, int) v) => halfUp(kpa ? asDouble(v) * kpaToMmhg : asDouble(v));
  final values = <String, int>{
    'systolic': mmhg(sys),
    'diastolic': mmhg(dia),
    'mean_arterial': mmhg(mean),
  };
  final exact = <String, String>{
    'systolic': asDecimal(sys),
    'diastolic': asDecimal(dia),
    'mean_arterial': asDecimal(mean),
  };
  if (pulse != null) {
    values['pulse'] = halfUp(asDouble(pulse));
    exact['pulse'] = asDecimal(pulse);
  }
  if (userId == 0xFF) userId = null; // "unknown user"
  return GattReading(
    kind: 'blood_pressure',
    characteristic: '2a35',
    values: values,
    exact: exact,
    unit: kpa ? 'kPa' : 'mmHg',
    deviceTime: deviceTime,
    userId: userId,
    flags: out,
  );
}

const Map<int, String> _plxMeas = {
  5: 'measurement_ongoing',
  6: 'early_estimate',
  7: 'validated',
  8: 'fully_qualified',
  9: 'from_device_storage',
  10: 'demonstration_data',
  11: 'testing_data',
  12: 'calibration_ongoing',
  13: 'measurement_unavailable',
  14: 'questionable_measurement',
  15: 'invalid_measurement',
};
const Map<int, String> _plxDevice = {
  0: 'extended_display_update',
  1: 'equipment_malfunction',
  2: 'signal_processing_irregularity',
  3: 'inadequate_signal',
  4: 'poor_signal',
  5: 'low_perfusion',
  6: 'erratic_signal',
  7: 'nonpulsatile_signal',
  8: 'questionable_pulse',
  9: 'signal_analysis_ongoing',
  10: 'sensor_interference',
  11: 'sensor_unconnected',
  12: 'unknown_sensor',
  13: 'sensor_displaced',
  14: 'sensor_malfunction',
  15: 'sensor_disconnected',
};

void _plxTail(_Reader r, bool hasMeas, bool hasDev, bool hasPai,
    Map<String, String> exact, List<String> flags) {
  if (hasMeas) flags.addAll(_bits(r.u16(), _plxMeas));
  if (hasDev) flags.addAll(_bits(r.u24(), _plxDevice));
  if (hasPai) {
    try {
      exact['perfusion_index'] = asDecimal(r.sf());
    } on GattError {
      flags.add('perfusion_index_unavailable');
    }
  }
}

GattReading _plx(String char, (int, int) spo2, (int, int) pr,
        Map<String, String> exact, String? deviceTime, List<String> flags) =>
    GattReading(
      kind: 'spo2',
      characteristic: char,
      values: {'spo2': halfUp(asDouble(spo2)), 'pulse': halfUp(asDouble(pr))},
      exact: {'spo2': asDecimal(spo2), 'pulse': asDecimal(pr), ...exact},
      unit: '%',
      deviceTime: deviceTime,
      userId: null,
      flags: flags,
    );

GattReading parsePlxSpotCheck(List<int> data) {
  final r = _Reader(data);
  final flags = r.u8();
  if (flags & 0xE0 != 0) throw GattError('reserved flag bits are set');
  final spo2 = r.sf(), pr = r.sf();
  String? deviceTime;
  final out = <String>[];
  final exact = <String, String>{};
  if (flags & 0x01 != 0) {
    final (iso, known) = r.dateTime();
    deviceTime = iso;
    if (!known) out.add('device_clock_not_set');
  }
  _plxTail(r, flags & 0x02 != 0, flags & 0x04 != 0, flags & 0x08 != 0, exact,
      out);
  if (flags & 0x10 != 0) out.add('device_clock_not_set');
  r.done();
  return _plx('2a5e', spo2, pr, exact, deviceTime, out);
}

/// Uses the "normal" SpO2/PR pair; the fast and slow pairs are skipped.
GattReading parsePlxContinuous(List<int> data) {
  final r = _Reader(data);
  final flags = r.u8();
  if (flags & 0xE0 != 0) throw GattError('reserved flag bits are set');
  final spo2 = r.sf(), pr = r.sf();
  if (flags & 0x01 != 0) r.take(4);
  if (flags & 0x02 != 0) r.take(4);
  final out = <String>[];
  final exact = <String, String>{};
  _plxTail(r, flags & 0x04 != 0, flags & 0x08 != 0, flags & 0x10 != 0, exact,
      out);
  r.done();
  return _plx('2a5f', spo2, pr, exact, null, out);
}

const supportedCharacteristics = {'2a35', '2a5e', '2a5f'};

List<int> hexToBytes(String hex) {
  if (hex.length.isOdd || !RegExp(r'^[0-9a-fA-F]*$').hasMatch(hex)) {
    throw GattError('raw payload is not hexadecimal');
  }
  return [
    for (var i = 0; i < hex.length; i += 2)
      int.parse(hex.substring(i, i + 2), radix: 16),
  ];
}

String bytesToHex(List<int> bytes) =>
    bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();

GattReading parseCharacteristic(String characteristic, String rawHex) {
  final char = characteristic.toLowerCase().replaceFirst('0x', '');
  final data = hexToBytes(rawHex);
  if (data.isEmpty || data.length > 64) {
    throw GattError('raw payload length is not plausible');
  }
  switch (char) {
    case '2a35':
      return parseBloodPressure(data);
    case '2a5e':
      return parsePlxSpotCheck(data);
    case '2a5f':
      return parsePlxContinuous(data);
  }
  throw GattError('unsupported characteristic $characteristic');
}

/// Flags that mean "not a finished measurement of this patient, now".
/// Mirrors REFUSE_FLAGS in the API, which enforces the same rule.
const refuseFlags = {
  'measurement_ongoing',
  'measurement_unavailable',
  'invalid_measurement',
  'from_device_storage',
  'demonstration_data',
  'testing_data',
  'calibration_ongoing',
  'equipment_malfunction',
  'sensor_unconnected',
  'sensor_disconnected',
  'sensor_malfunction',
};

String? refusalReason(GattReading r) {
  final bad = r.flags.where(refuseFlags.contains).toList()..sort();
  return bad.isEmpty ? null : 'device marks this reading as: ${bad.join(', ')}';
}
