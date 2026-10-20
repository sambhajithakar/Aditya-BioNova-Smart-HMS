/// PDF documents the app can print or share (package `pdf`, Apache-2.0).
///
/// * [buildRxDraftPdf] — a PREVIEW of a prescription draft written on the
///   device, watermarked on every page "DRAFT - not valid until signed
///   online" plus a banner. It is never a valid prescription.
/// * [buildSignedRxPdf] — a signed prescription, built ONLY from the
///   server's `GET /prescriptions/{id}` answer, and only when the server
///   says `status == "signed"` with a `signed_at` — never from local data.
/// * [buildReceiptPdf] — a bill/receipt built ONLY from the server's
///   `GET /billing/invoices/{id}` answer (server-computed totals and
///   payments; the device never invents an amount).
///
/// Fonts: the built-in PDF Helvetica (no font asset in the APK — small
/// download for low-cost phones). It covers Latin-1 / Windows-1252 only, so
/// text outside it (e.g. a patient name typed in Devanagari) is
/// transliterated to `?` by [pdfSafe]; drug names, doses, codes and
/// amounts are Latin already. Embedding a Devanagari font is a follow-up.
library;

import 'dart:typed_data';

import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;

/// The watermark every draft page carries (also asserted by tests). A
/// plain hyphen: the built-in PDF font is Latin-1 only.
const String kDraftWatermark = 'DRAFT - not valid until signed online';

class RxSignatureMissing implements Exception {
  const RxSignatureMissing();

  @override
  String toString() =>
      'The server has not signed this prescription — it cannot be printed '
      'as a signed prescription.';
}

/// Keep characters the built-in Helvetica can encode (Latin-1); common
/// typographic punctuation is mapped to ASCII, anything else becomes '?'.
/// (The `pdf` package silently DROPS a whole text run it cannot encode.)
String pdfSafe(Object? value) {
  final s = '${value ?? ''}';
  final out = StringBuffer();
  for (final r in s.runes) {
    final mapped = switch (r) {
      0x2013 || 0x2014 => '-',
      0x2018 || 0x2019 => "'",
      0x201c || 0x201d => '"',
      0x2022 => '*',
      0x20b9 => 'Rs.',
      _ => null,
    };
    if (mapped != null) {
      out.write(mapped);
    } else if ((r >= 0x20 && r <= 0x7e) || (r >= 0xa0 && r <= 0xff) || r == 0x0a) {
      out.writeCharCode(r);
    } else {
      out.write('?');
    }
  }
  return out.toString();
}

String _money(Object? v) {
  final n = v is num ? v : num.tryParse('$v') ?? 0;
  return 'Rs. ${n.toStringAsFixed(2)}';
}

pw.Widget _header(String clinic, String title) => pw.Column(
      crossAxisAlignment: pw.CrossAxisAlignment.start,
      children: [
        pw.Text(pdfSafe(clinic),
            style: pw.TextStyle(fontSize: 16, fontWeight: pw.FontWeight.bold)),
        pw.SizedBox(height: 2),
        pw.Text(pdfSafe(title), style: const pw.TextStyle(fontSize: 12)),
        pw.Divider(),
      ],
    );

/// Prescription DRAFT preview from the device's draft (see library doc).
Future<Uint8List> buildRxDraftPdf({
  required Map<String, dynamic> draft,
  required String clinicName,
  String prescriber = '',
  bool compress = true,
}) async {
  final doc = pw.Document(
    compress: compress,
    title: 'Prescription draft',
    creator: 'Aditya BioNova Smart HMS',
  );
  final items = (draft['items'] as List<dynamic>? ?? const [])
      .whereType<Map<dynamic, dynamic>>()
      .toList();
  doc.addPage(
    pw.MultiPage(
      pageTheme: pw.PageTheme(
        pageFormat: PdfPageFormat.a5,
        margin: const pw.EdgeInsets.all(24),
        buildBackground: (ctx) => pw.FullPage(
          ignoreMargins: true,
          child: pw.Center(
            child: pw.Transform.rotate(
              angle: 0.6,
              child: pw.Text(
                kDraftWatermark,
                style: pw.TextStyle(
                    fontSize: 22,
                    color: PdfColor.fromInt(0x33B3261E),
                    fontWeight: pw.FontWeight.bold),
              ),
            ),
          ),
        ),
      ),
      header: (ctx) => pw.Container(
        padding: const pw.EdgeInsets.all(4),
        color: PdfColor.fromInt(0xFFFDE7E9),
        child: pw.Text(kDraftWatermark,
            style: pw.TextStyle(
                fontSize: 10,
                color: PdfColor.fromInt(0xFFB3261E),
                fontWeight: pw.FontWeight.bold)),
      ),
      build: (ctx) => [
        _header(clinicName, 'Prescription (draft preview)'),
        pw.Text('Patient: ${pdfSafe(draft['patientLabel'])}'),
        if ('${draft['diagnosis'] ?? ''}'.isNotEmpty)
          pw.Text('Diagnosis: ${pdfSafe(draft['diagnosis'])}'),
        if (prescriber.isNotEmpty) pw.Text('Prescriber: ${pdfSafe(prescriber)}'),
        pw.SizedBox(height: 8),
        pw.TableHelper.fromTextArray(
          headers: const ['Medicine', 'Dose', 'Frequency', 'Days', 'Qty'],
          data: [
            for (final it in items)
              [
                pdfSafe(it['drug_name'] ?? it['drug_id']),
                pdfSafe(it['dose']),
                pdfSafe(it['frequency']),
                pdfSafe(it['duration_days']),
                pdfSafe(it['dispense_quantity'] ?? ''),
              ],
          ],
          cellStyle: const pw.TextStyle(fontSize: 9),
          headerStyle: pw.TextStyle(fontSize: 9, fontWeight: pw.FontWeight.bold),
        ),
        pw.SizedBox(height: 12),
        pw.Text(
          'This preview was generated on a device and has NOT been checked '
          'or signed by the server. Dispensing is not permitted against it.',
          style: const pw.TextStyle(fontSize: 8),
        ),
      ],
    ),
  );
  return doc.save();
}

/// Signed prescription from the SERVER answer only.
Future<Uint8List> buildSignedRxPdf({
  required Map<String, dynamic> serverRx,
  required String clinicName,
  bool compress = true,
}) async {
  if (serverRx['status'] != 'signed' || serverRx['signed_at'] == null) {
    throw const RxSignatureMissing();
  }
  final doc = pw.Document(compress: compress, title: 'Prescription');
  final items = (serverRx['items'] as List<dynamic>? ?? const [])
      .whereType<Map<dynamic, dynamic>>()
      .toList();
  final prescriber = serverRx['prescriber'];
  doc.addPage(
    pw.MultiPage(
      pageFormat: PdfPageFormat.a5,
      margin: const pw.EdgeInsets.all(24),
      build: (ctx) => [
        _header(clinicName, 'Prescription'),
        pw.Text('Prescription id: ${pdfSafe(serverRx['id'])}  '
            'version ${pdfSafe(serverRx['version'])}'),
        pw.Text('Signed at (server): ${pdfSafe(serverRx['signed_at'])}'),
        if (prescriber is Map)
          pw.Text('Prescriber: ${pdfSafe(prescriber['full_name'])} '
              '${pdfSafe(prescriber['registration_number'] ?? '')}'),
        if ('${serverRx['diagnosis_text'] ?? ''}'.isNotEmpty)
          pw.Text('Diagnosis: ${pdfSafe(serverRx['diagnosis_text'])}'),
        pw.SizedBox(height: 8),
        pw.TableHelper.fromTextArray(
          headers: const ['Medicine', 'Dose', 'Route', 'Frequency', 'Days'],
          data: [
            for (final it in items)
              [
                pdfSafe(it['drug_name'] ?? it['generic_name'] ?? it['drug_id']),
                pdfSafe(it['dose']),
                pdfSafe(it['route']),
                pdfSafe(it['frequency']),
                pdfSafe(it['duration_days']),
              ],
          ],
          cellStyle: const pw.TextStyle(fontSize: 9),
          headerStyle: pw.TextStyle(fontSize: 9, fontWeight: pw.FontWeight.bold),
        ),
        if ('${serverRx['advice'] ?? ''}'.isNotEmpty) ...[
          pw.SizedBox(height: 8),
          pw.Text('Advice: ${pdfSafe(serverRx['advice'])}'),
        ],
        if ('${serverRx['follow_up'] ?? ''}'.isNotEmpty)
          pw.Text('Follow-up: ${pdfSafe(serverRx['follow_up'])}'),
      ],
    ),
  );
  return doc.save();
}

/// Bill / receipt from the SERVER invoice detail only.
Future<Uint8List> buildReceiptPdf({
  required Map<String, dynamic> serverInvoice,
  required String clinicName,
  bool compress = true,
}) async {
  if (serverInvoice['invoice_number'] == null) {
    throw ArgumentError('Not a server invoice (no invoice_number).');
  }
  final doc = pw.Document(compress: compress, title: 'Receipt');
  final items = (serverInvoice['items'] as List<dynamic>? ?? const [])
      .whereType<Map<dynamic, dynamic>>()
      .toList();
  final payments = (serverInvoice['payments'] as List<dynamic>? ?? const [])
      .whereType<Map<dynamic, dynamic>>()
      .toList();
  doc.addPage(
    pw.MultiPage(
      pageFormat: PdfPageFormat.a5,
      margin: const pw.EdgeInsets.all(24),
      build: (ctx) => [
        _header(clinicName,
            'Invoice ${pdfSafe(serverInvoice['invoice_number'])} - '
            '${pdfSafe(serverInvoice['status'])}'),
        pw.TableHelper.fromTextArray(
          headers: const ['Item', 'Qty', 'Unit price', 'Amount'],
          data: [
            for (final it in items)
              [
                pdfSafe(it['description']),
                pdfSafe(it['quantity']),
                _money(it['unit_price']),
                _money(it['line_total'] ?? it['amount'] ??
                    ((it['quantity'] as num? ?? 0) *
                        (it['unit_price'] as num? ?? 0))),
              ],
          ],
          cellStyle: const pw.TextStyle(fontSize: 9),
          headerStyle: pw.TextStyle(fontSize: 9, fontWeight: pw.FontWeight.bold),
        ),
        pw.SizedBox(height: 8),
        pw.Text('Subtotal: ${_money(serverInvoice['subtotal'])}'),
        pw.Text('Discount: ${_money(serverInvoice['discount'])}'),
        pw.Text('Tax: ${_money(serverInvoice['tax_total'])}'),
        pw.Text('Total: ${_money(serverInvoice['total'])}',
            style: pw.TextStyle(fontWeight: pw.FontWeight.bold)),
        pw.Text('Paid: ${_money(serverInvoice['amount_paid'])}'),
        if (payments.isNotEmpty) ...[
          pw.SizedBox(height: 8),
          pw.Text('Payments (server records):'),
          for (final p in payments)
            pw.Text('  ${pdfSafe(p['method'])} ${_money(p['amount'])} '
                '${pdfSafe(p['status'] ?? '')} ${pdfSafe(p['created_at'] ?? '')}'),
        ],
        pw.SizedBox(height: 12),
        pw.Text('Amounts as computed and recorded by the server.',
            style: const pw.TextStyle(fontSize: 8)),
      ],
    ),
  );
  return doc.save();
}
