/// Billing tab: raise an invoice with no network.
///
/// The invoice is queued with a per-day, per-patient, per-line dedupe key
/// (a double-tap stays ONE op) and pushed with its `Idempotency-Key`, so a
/// retry after a flaky connection can never charge the patient twice. The
/// server computes the totals — the device never invents an amount, and a
/// payment is only ever taken against a server-issued invoice.
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../l10n/l10n.dart';
import '../settings/app_settings.dart';
import '../sync/outbox.dart';
import '../util/dates.dart';
import '../data/directory.dart';
import '../pdf/documents.dart';
import 'sync_widgets.dart';

const List<String> _itemTypes = [
  'consultation',
  'procedure',
  'pharmacy',
  'lab',
  'other',
];

class BillingTab extends StatefulWidget {
  const BillingTab({super.key, required this.graph});

  final AppGraph graph;

  @override
  State<BillingTab> createState() => _BillingTabState();
}

class _BillingTabState extends State<BillingTab> {
  String? _patientId;
  String _itemType = 'consultation';
  final _description = TextEditingController();
  final _quantity = TextEditingController(text: '1');
  final _price = TextEditingController();
  String? _error;
  String? _notice;

  @override
  void initState() {
    super.initState();
    _patientId =
        widget.graph.directory.resolveSelection(null, widget.graph.idMap);
  }

  /// Never a raw device id: server id, or `$ref:` until it syncs (H24).
  String _patientRef(String id) =>
      widget.graph.directory.refFor(id, widget.graph.idMap);

  Future<void> _saveInvoice() async {
    final patientId =
        widget.graph.directory.resolveSelection(_patientId, widget.graph.idMap);
    final description = _description.text.trim();
    if (patientId == null) {
      setState(() => _error = context.l10n.pickPatientFirst);
      return;
    }
    if (description.isEmpty) {
      setState(() => _error = context.l10n.billingDescribe);
      return;
    }
    final quantity = int.tryParse(_quantity.text.trim()) ?? 0;
    final price = double.tryParse(_price.text.trim()) ?? 0;
    if (quantity < 1 || price <= 0) {
      setState(() => _error = context.l10n.billingQtyPrice);
      return;
    }

    final branchId = widget.graph.directory.branches.isNotEmpty
        ? widget.graph.directory.branches.first['id'] as String?
        : null;
    // D10: the key covers everything that makes two lines different —
    // type, description, quantity and unit price — on the local day (D12).
    // Only a true double-tap of the SAME line collapses into one op.
    final dedupeKey = 'invoice:$patientId:$_itemType:'
        '${description.toLowerCase()}:$quantity:${price.toStringAsFixed(2)}:'
        '${localDay()}';
    final existing = widget.graph.outbox.openOpFor(dedupeKey);
    final op = widget.graph.outbox.enqueue(
      entity: 'invoice',
      method: 'POST',
      path: '/billing/invoices',
      payload: {
        'patient_id': _patientRef(patientId),
        'branch_id': branchId,
        'discount': 0,
        'items': [
          {
            'item_type': _itemType,
            'description': description,
            'quantity': quantity,
            'unit_price': price,
            'tax_rate': 0,
          },
        ],
      },
      dedupeKey: dedupeKey,
    );

    if (existing != null && existing.id == op.id) {
      setState(() {
        _error = null;
        _notice = context.l10n.billingDuplicate;
      });
      return;
    }

    widget.graph.scheduler.requestSync();
    setState(() {
      _error = null;
      _notice = context.l10n.billingSaved;
      _description.clear();
      _price.clear();
      _quantity.text = '1';
    });
  }

  List<Map<String, dynamic>>? _recent;
  bool _recentOffline = false;

  /// Server invoices (online only — totals are the server's).
  Future<void> _loadRecent() async {
    try {
      final page = await widget.graph.client.listInvoices();
      if (!mounted) return;
      setState(() {
        _recent = DirectoryCache.listOf(page['items']);
        _recentOffline = false;
      });
    } catch (_) {
      if (mounted) setState(() => _recentOffline = true);
    }
  }

  Future<void> _receipt(String id) async {
    try {
      final inv = await widget.graph.client.getInvoice(id);
      final bytes = await buildReceiptPdf(
        serverInvoice: inv,
        clinicName:
            widget.graph.session.cachedProfile?.organizationName ?? '',
      );
      await widget.graph.pdfOutput
          .share(bytes, 'invoice-${inv['invoice_number']}.pdf');
    } catch (err) {
      if (mounted) setState(() => _error = err.toString());
    }
  }

  /// Confirm a payment: ONLINE, server-verified, explicit confirmation,
  /// one Idempotency-Key per confirmation (a double tap cannot charge
  /// twice). Never queued offline.
  Future<void> _confirmPayment(Map<String, dynamic> inv) async {
    final l = context.l10n;
    final due = ((inv['total'] as num? ?? 0) - (inv['amount_paid'] as num? ?? 0))
        .toDouble();
    final amount = TextEditingController(text: due.toStringAsFixed(2));
    var method = 'cash';
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => AlertDialog(
          title: Text(l.paymentTitle('${inv['invoice_number']}')),
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(
              key: const Key('payment-amount'),
              controller: amount,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: InputDecoration(labelText: l.paymentAmount),
            ),
            DropdownButton<String>(
              key: const Key('payment-method'),
              value: method,
              isExpanded: true,
              items: [
                for (final m in const ['cash', 'upi', 'card', 'insurance', 'other'])
                  DropdownMenuItem(value: m, child: Text(m.toUpperCase())),
              ],
              onChanged: (v) => setLocal(() => method = v ?? 'cash'),
            ),
            Text(l.paymentServerNote),
          ]),
          actions: [
            TextButton(
                key: const Key('confirm-cancel'),
                onPressed: () => Navigator.of(ctx).pop(false),
                child: Text(l.cancel)),
            FilledButton(
                key: const Key('confirm-ok'),
                onPressed: () => Navigator.of(ctx).pop(true),
                child: Text(l.paymentConfirm)),
          ],
        ),
      ),
    );
    final value = double.tryParse(amount.text.trim());
    amount.dispose();
    if (ok != true || value == null || value <= 0) return;
    try {
      await widget.graph.client.recordPayment(
        invoiceId: '${inv['id']}',
        amount: value,
        method: method,
        idempotencyKey: Outbox.newId(),
      );
      if (!mounted) return;
      setState(() => _notice = l.paymentRecorded);
      await _loadRecent();
    } catch (err) {
      if (mounted) setState(() => _error = err.toString());
    }
  }

  Widget _invoiceTile(Map<String, dynamic> inv) {
    final l = context.l10n;
    final id = '${inv['id']}';
    final paid = inv['status'] == 'paid';
    return Card(
      key: Key('invoice-$id'),
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${inv['invoice_number'] ?? ''} · '
                '${widget.graph.directory.patientLabel('${inv['patient_id']}')}'),
            Text(l.invoiceAmounts('${inv['total']}', '${inv['amount_paid']}',
                '${inv['status']}')),
            Wrap(children: [
              OnlineOnlyButton(
                key: Key('invoice-receipt-$id'),
                network: widget.graph.network,
                icon: Icons.picture_as_pdf_outlined,
                label: l.invoiceReceipt,
                onPressed: () => _receipt(id),
              ),
              if (!paid)
                OnlineOnlyButton(
                  key: Key('invoice-pay-$id'),
                  network: widget.graph.network,
                  icon: Icons.payments_outlined,
                  label: l.paymentConfirm,
                  onPressed: () => _confirmPayment(inv),
                ),
            ]),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final directory = widget.graph.directory;
    final outbox = widget.graph.outbox;
    final l = context.l10n;
    final itemHeight = widget.graph.settings.ruralMode
        ? kRuralTouchTarget + 8
        : kMinInteractiveDimension;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(l.billingTitle,
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 12),
        Text(l.patient, style: Theme.of(context).textTheme.labelLarge),
        DropdownButton<String>(
          key: const Key('billing-patient'),
          isExpanded: true,
          itemHeight: itemHeight,
          value: directory.resolveSelection(_patientId, widget.graph.idMap),
          hint: const Text('—'),
          items: [
            for (final p in directory.patients)
              DropdownMenuItem<String>(
                value: p['id'] as String,
                child: Text(directory.pickerLabel(p, widget.graph.idMap,
                    pendingTag: l.pendingSyncTag, syncedTag: l.syncedTag)),
              ),
          ],
          onChanged: (v) => setState(() => _patientId = v),
        ),
        const SizedBox(height: 12),
        Text(l.billingLineType, style: Theme.of(context).textTheme.labelLarge),
        DropdownButton<String>(
          key: const Key('billing-item-type'),
          value: _itemType,
          isExpanded: true,
          itemHeight: itemHeight,
          items: [
            for (final t in _itemTypes)
              DropdownMenuItem(value: t, child: Text(itemTypeLabel(l, t))),
          ],
          onChanged: (v) => setState(() => _itemType = v ?? 'consultation'),
        ),
        const SizedBox(height: 12),
        TextField(
          key: const Key('billing-description'),
          controller: _description,
          decoration: InputDecoration(labelText: l.billingDescription),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: TextField(
                key: const Key('billing-quantity'),
                controller: _quantity,
                keyboardType: TextInputType.number,
                decoration: InputDecoration(labelText: l.billingQuantity),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextField(
                key: const Key('billing-price'),
                controller: _price,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                decoration: InputDecoration(labelText: l.billingUnitPrice),
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        FilledButton(
          key: const Key('billing-add'),
          onPressed: _saveInvoice,
          child: Text(l.billingAdd),
        ),
        if (_notice != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_notice!, key: const Key('billing-notice')),
          ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              _error!,
              key: const Key('billing-error'),
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        const SizedBox(height: 16),
        Text(
          l.outboxCounts(
            outbox.count(OpStatus.pending),
            outbox.count(OpStatus.failed),
            outbox.count(OpStatus.conflicted),
          ),
          key: const Key('billing-outbox-counts'),
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 16),
        Row(children: [
          Expanded(
            child: Text(l.billingRecent,
                style: Theme.of(context).textTheme.titleSmall),
          ),
          TextButton(
            key: const Key('billing-recent-load'),
            onPressed: _loadRecent,
            child: Text(_recent == null ? l.billingRecentShow : l.refresh),
          ),
        ]),
        if (_recentOffline) const NeedsConnectionPanel(),
        if (_recent != null && !_recentOffline)
          for (final inv in _recent!) _invoiceTile(inv),
      ],
    );
  }
}
