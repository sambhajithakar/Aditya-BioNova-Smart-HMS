/// Camera scanner (device only — tests use `FakeCodeScanner`).
///
/// Low-cost phones: the controller asks only for the formats the purpose
/// needs (QR for check-in; DataMatrix / Code 128 / EAN for medicine packs),
/// `DetectionSpeed.noDuplicates`, no image capture, and the camera stops as
/// soon as one code is read. A "type the code" fallback covers phones whose
/// camera cannot focus close enough.
library;

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../l10n/l10n.dart';
import '../scan/scanner.dart';

class CameraCodeScanner implements CodeScanner {
  const CameraCodeScanner();

  @override
  Future<String?> scan(BuildContext context, ScanPurpose purpose) =>
      Navigator.of(context).push<String>(
        MaterialPageRoute<String>(
          fullscreenDialog: true,
          builder: (_) => ScanScreen(purpose: purpose),
        ),
      );
}

class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key, required this.purpose});

  final ScanPurpose purpose;

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  late final MobileScannerController _controller = MobileScannerController(
    detectionSpeed: DetectionSpeed.noDuplicates,
    formats: widget.purpose == ScanPurpose.checkIn
        ? const [BarcodeFormat.qrCode]
        : const [
            BarcodeFormat.dataMatrix,
            BarcodeFormat.code128,
            BarcodeFormat.ean13,
            BarcodeFormat.qrCode,
          ],
  );
  bool _done = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _finish(String? value) {
    if (_done) return;
    _done = true;
    Navigator.of(context).pop(value);
  }

  Future<void> _manual() async {
    final ctl = TextEditingController();
    final l = context.l10n;
    final value = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l.scanTypeCode),
        content: TextField(
          key: const Key('scan-manual-field'),
          controller: ctl,
          autofocus: true,
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: Text(l.cancel)),
          FilledButton(
              onPressed: () => Navigator.of(ctx).pop(ctl.text.trim()),
              child: Text(l.scanUse)),
        ],
      ),
    );
    ctl.dispose();
    if (value != null && value.isNotEmpty) _finish(value);
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.purpose == ScanPurpose.checkIn
            ? l.scanCheckInTitle
            : l.scanBatchTitle),
      ),
      body: Column(
        children: [
          Expanded(
            child: MobileScanner(
              controller: _controller,
              onDetect: (capture) {
                for (final b in capture.barcodes) {
                  final v = b.rawValue;
                  if (v != null && v.isNotEmpty) {
                    _finish(v);
                    return;
                  }
                }
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Text(widget.purpose == ScanPurpose.checkIn
                ? l.scanCheckInHelp
                : l.scanBatchHelp),
          ),
          TextButton(onPressed: _manual, child: Text(l.scanTypeCode)),
          const SizedBox(height: 12),
        ],
      ),
    );
  }
}
