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
      ],
    );
  }
}
