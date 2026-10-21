/// Byte encoders for the simulator (M8.2c): builds Blood Pressure (0x2A35)
/// and PLX Spot-Check (0x2A5E) payloads field by field from the
/// specification layout. SYNTHETIC only — never used for real devices.
library;

List<int> sfloatBytes(int mantissa, [int exponent = 0]) {
  final raw = ((exponent & 0xF) << 12) | (mantissa & 0x0FFF);
  return [raw & 0xFF, raw >> 8];
}

List<int> _u16(int v) => [v & 0xFF, (v >> 8) & 0xFF];

List<int> dateTimeBytes(DateTime t) =>
    [..._u16(t.year), t.month, t.day, t.hour, t.minute, t.second];

/// [deviceClock]: the device's LOCAL wall-clock time (null = no time stamp).
List<int> encodeBloodPressure({
  required int systolic,
  required int diastolic,
  required int mean,
  int? pulse,
  DateTime? deviceClock,
  int status = -1,
}) {
  var flags = 0;
  final body = <int>[
    ...sfloatBytes(systolic),
    ...sfloatBytes(diastolic),
    ...sfloatBytes(mean),
  ];
  if (deviceClock != null) {
    flags |= 0x02;
    body.addAll(dateTimeBytes(deviceClock));
  }
  if (pulse != null) {
    flags |= 0x04;
    body.addAll(sfloatBytes(pulse));
  }
  if (status >= 0) {
    flags |= 0x10;
    body.addAll(_u16(status));
  }
  return [flags, ...body];
}

List<int> encodePlxSpotCheck({
  required int spo2,
  required int pulse,
  DateTime? deviceClock,
  int measurementStatus = -1,
}) {
  var flags = 0;
  final body = <int>[...sfloatBytes(spo2), ...sfloatBytes(pulse)];
  if (deviceClock != null) {
    flags |= 0x01;
    body.addAll(dateTimeBytes(deviceClock));
  }
  if (measurementStatus >= 0) {
    flags |= 0x02;
    body.addAll(_u16(measurementStatus));
  }
  return [flags, ...body];
}
