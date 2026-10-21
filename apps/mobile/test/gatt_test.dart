// M8.2a: the Dart GATT parser reproduces every SYNTHETIC vector that the
// API's Python parser is tested against (packages/contracts/device_vectors.json).
import 'dart:convert';
import 'dart:io';

import 'package:aditya_bionova_mobile/devices/gatt.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final doc = jsonDecode(
          File('../../packages/contracts/device_vectors.json').readAsStringSync())
      as Map<String, dynamic>;
  final vectors = (doc['vectors'] as List).cast<Map<String, dynamic>>();

  test('the shared vector file is present and non-trivial', () {
    expect(vectors.length, greaterThanOrEqualTo(20));
  });

  for (final v in vectors) {
    test('vector: ${v['name']}', () {
      final char = v['characteristic'] as String;
      final hex = v['hex'] as String;
      if (v.containsKey('error')) {
        expect(
          () => parseCharacteristic(char, hex),
          throwsA(isA<GattError>().having(
              (e) => e.message, 'message', contains(v['error'] as String))),
        );
      } else {
        // JSON round-trip so map/list types compare like the API's dict
        final got = jsonDecode(jsonEncode(parseCharacteristic(char, hex).toJson()));
        expect(got, v['expect']);
      }
    });
  }

  test('SFLOAT sign extension, exact decimals, half-up rounding', () {
    expect(sfloat(0x0FFF), (-1, 0));
    expect(sfloat(0xF4B5), (0x4B5, -1));
    expect(asDecimal((1205, -1)), '120.5');
    expect(asDecimal((5, -2)), '0.05');
    expect(asDecimal((-15, -1)), '-1.5');
    expect(asDecimal((3, 2)), '300');
    expect([0.5, 1.49, 132.5, 84.5, -1.5].map(halfUp), [1, 1, 133, 85, -2]);
    for (final s in [0x07FF, 0x0800, 0x07FE, 0x0802, 0x0801]) {
      expect(() => sfloat(s), throwsA(isA<GattError>()));
    }
  });

  test('capture policy refuses stored / ongoing readings, not movement flags', () {
    GattReading byName(String n) => parseCharacteristic(
        vectors.firstWhere((v) => v['name'] == n)['characteristic'] as String,
        vectors.firstWhere((v) => v['name'] == n)['hex'] as String);
    expect(refusalReason(byName('spot from storage is reported (and refused by policy)')),
        contains('from_device_storage'));
    expect(refusalReason(byName('continuous with fast, slow, status, PAI')),
        contains('measurement_ongoing'));
    expect(refusalReason(byName('bp all fields')), isNull);
  });
}
