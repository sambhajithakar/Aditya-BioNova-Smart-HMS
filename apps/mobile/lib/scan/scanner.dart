/// Barcode / QR scanning behind an interface.
///
/// The device implementation opens [ScanScreen] (camera preview via
/// `mobile_scanner`, BSD-3-Clause) and returns the first code read; tests
/// inject a fake that returns a fixed string, so no widget test touches the
/// camera or a platform channel.
library;

import 'package:flutter/widgets.dart';

enum ScanPurpose { checkIn, medicineBatch }

abstract interface class CodeScanner {
  /// The scanned text, or null when the user cancelled.
  Future<String?> scan(BuildContext context, ScanPurpose purpose);
}

/// Test / manual-entry double.
class FakeCodeScanner implements CodeScanner {
  FakeCodeScanner(this.results);

  final List<String?> results;
  int calls = 0;

  @override
  Future<String?> scan(BuildContext context, ScanPurpose purpose) async {
    calls += 1;
    return results.isEmpty ? null : results.removeAt(0);
  }
}
