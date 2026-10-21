/// Where generated PDFs go: the Android share sheet / print dialog on the
/// device (package `printing`, Apache-2.0), a recorder in tests.
library;

import 'dart:typed_data';

import 'package:printing/printing.dart';

abstract interface class PdfOutput {
  Future<void> share(Uint8List bytes, String filename);
}

class PrintingPdfOutput implements PdfOutput {
  const PrintingPdfOutput();

  @override
  Future<void> share(Uint8List bytes, String filename) async {
    await Printing.sharePdf(bytes: bytes, filename: filename);
  }
}

/// Test double: remembers what would have been shared.
class RecordingPdfOutput implements PdfOutput {
  final List<(String, Uint8List)> shared = [];

  @override
  Future<void> share(Uint8List bytes, String filename) async {
    shared.add((filename, bytes));
  }
}
