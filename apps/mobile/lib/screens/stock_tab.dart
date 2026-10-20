/// Stock tab (pharmacy): inventory COUNT drafts with batch-barcode scanning.
///
/// Scan a medicine pack (GS1 DataMatrix: GTIN, batch, expiry) or an
/// in-house SKU label; the item is matched against the cached inventory
/// list (no PHI); type the counted quantity → saved on the device. Posting
/// the difference as a stock adjustment changes the books, so it is
/// ONLINE-ONLY: the server's current quantity-on-hand is re-read, the
/// difference shown, and only after confirmation is the adjustment posted
/// (with its own Idempotency-Key).
library;

import 'package:flutter/material.dart';

import '../api/transport.dart';
import '../app_graph.dart';
import '../data/directory.dart';
import '../l10n/l10n.dart';
import '../scan/gs1.dart';
import '../scan/scanner.dart';
import 'sync_tab.dart' show confirmDialog;
import 'sync_widgets.dart';

class StockTab extends StatefulWidget {
  const StockTab({super.key, required this.graph});

  final AppGraph graph;

  @override
  State<StockTab> createState() => _StockTabState();
}

class _StockTabState extends State<StockTab> {
  Map<String, dynamic>? _item;
  Gs1Data? _scan;
  final _qty = TextEditingController();
  String? _notice;
  String? _error;

  AppGraph get graph => widget.graph;

  @override
  void initState() {
    super.initState();
    _refreshItems();
  }

  @override
  void dispose() {
    _qty.dispose();
    super.dispose();
  }

  Future<void> _refreshItems() async {
    try {
      final page = await graph.client.listInventoryItems();
      await graph.stock.replaceItems(DirectoryCache.listOf(page['items']));
      if (mounted) setState(() {});
    } catch (_) {
      // offline: cached item list
    }
  }

  Future<void> _scanCode() async {
    final raw = await graph.scanner.scan(context, ScanPurpose.medicineBatch);
    if (raw == null || !mounted) return;
    final data = parseGs1(raw);
    final item = graph.stock.matchItem(
        sku: data.isGs1 ? null : data.raw, gtin: data.gtin);
    setState(() {
      _scan = data;
      _item = item;
      _error = item == null ? context.l10n.stockNoMatch(data.gtin ?? data.raw) : null;
      _notice = null;
    });
  }

  Future<void> _save() async {
    final l = context.l10n;
    final item = _item;
    final counted = int.tryParse(_qty.text.trim());
    if (item == null) {
      setState(() => _error = l.stockPickItem);
      return;
    }
    if (counted == null || counted < 0) {
      setState(() => _error = l.stockQtyInvalid);
      return;
    }
    await graph.stock.addCount(
      itemId: '${item['id']}',
      itemName: '${item['name'] ?? ''}',
      counted: counted,
      batch: _scan?.batch ?? '',
      expiry: _scan?.expiryText ?? '',
      code: _scan?.raw ?? '',
    );
    if (!mounted) return;
    setState(() {
      _error = null;
      _notice = l.stockSaved;
      _qty.clear();
      _scan = null;
    });
  }

  Future<void> _post(Map<String, dynamic> count) async {
    final l = context.l10n;
    try {
      final page = await graph.client.listInventoryItems();
      final items = DirectoryCache.listOf(page['items']);
      await graph.stock.replaceItems(items);
      final current = items.firstWhere((i) => i['id'] == count['itemId'],
          orElse: () => const {});
      if (current.isEmpty) throw ApiException(404, l.stockNoMatch('${count['itemName']}'));
      final onHand = (current['quantity_on_hand'] as num?)?.toInt() ?? 0;
      final delta = (count['counted'] as int) - onHand;
      if (!mounted) return;
      if (delta == 0) {
        await graph.stock.markPosted('${count['id']}');
        setState(() => _notice = l.stockNoDifference);
        return;
      }
      final ok = await confirmDialog(context,
          title: l.stockPostTitle('${count['itemName']}'),
          body: l.stockPostBody(onHand, count['counted'] as int, delta),
          action: l.stockPostAction);
      if (!ok) return;
      await graph.client.postStockAdjustment(
        itemId: '${count['itemId']}',
        quantity: delta,
        reason: 'Physical count ${count['batch'] ?? ''}'.trim(),
        idempotencyKey: '${count['id']}',
      );
      await graph.stock.markPosted('${count['id']}');
      if (mounted) setState(() => _notice = l.stockPosted);
    } catch (err) {
      if (mounted) setState(() => _error = err.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final items = graph.stock.items;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(l.stockTitle, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        FilledButton.icon(
          key: const Key('stock-scan'),
          onPressed: _scanCode,
          icon: const Icon(Icons.qr_code_scanner),
          label: Text(l.stockScan),
        ),
        DropdownButton<String>(
          key: const Key('stock-item'),
          isExpanded: true,
          value: _item?['id'] as String?,
          hint: Text(l.stockPickItem),
          items: [
            for (final it in items)
              DropdownMenuItem<String>(
                value: it['id'] as String,
                child: Text('${it['name'] ?? ''} (${it['sku'] ?? ''})'),
              ),
          ],
          onChanged: (v) => setState(() =>
              _item = items.firstWhere((i) => i['id'] == v)),
        ),
        if (_scan != null && _scan!.isGs1)
          Text(
            l.stockScanned(_scan!.batch ?? '—', _scan!.expiryText),
            key: const Key('stock-scanned'),
          ),
        TextField(
          key: const Key('stock-qty'),
          controller: _qty,
          keyboardType: TextInputType.number,
          decoration: InputDecoration(labelText: l.stockCounted),
        ),
        const SizedBox(height: 12),
        FilledButton(
          key: const Key('stock-save'),
          onPressed: _save,
          child: Text(l.stockSave),
        ),
        if (_notice != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_notice!, key: const Key('stock-notice')),
          ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_error!,
                key: const Key('stock-error'),
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
        const SizedBox(height: 16),
        Text(l.stockDrafts, style: Theme.of(context).textTheme.titleSmall),
        for (final c in graph.stock.counts)
          ListTile(
            key: Key('stock-count-${c['id']}'),
            contentPadding: EdgeInsets.zero,
            title: Text('${c['itemName']} · ${c['counted']}'),
            subtitle: Text([
              if ('${c['batch']}'.isNotEmpty) l.stockBatch('${c['batch']}'),
              if ('${c['expiry']}'.isNotEmpty) l.stockExpiry('${c['expiry']}'),
              c['posted'] == true ? l.stockPosted : l.statusSavedOnDevice,
            ].join(' · ')),
            trailing: c['posted'] == true
                ? null
                : OnlineOnlyButton(
                    key: Key('stock-post-${c['id']}'),
                    network: graph.network,
                    label: l.stockPostAction,
                    onPressed: () => _post(c),
                  ),
          ),
      ],
    );
  }
}
