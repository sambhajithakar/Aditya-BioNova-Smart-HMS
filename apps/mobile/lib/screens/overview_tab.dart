/// Overview tab (hospital administrator) and the mobile "Today's summary".
///
/// Reports are ONLINE-ONLY: they are computed by the server from its
/// ledger (`GET /reports/summary?from=today&to=today`, needs `report.read`)
/// and `GET /appointments` for today's count. Nothing is cached on the
/// device; offline the card says "Needs connection". Below it, the sync
/// health of THIS device (counts per status) — available offline.
library;

import 'package:flutter/material.dart';

import '../api/transport.dart';
import '../app_graph.dart';
import '../l10n/l10n.dart';
import '../sync/sync_status.dart';
import 'sync_widgets.dart';

/// Today's numbers from the server (or why they are unavailable).
class TodaySummary {
  const TodaySummary({
    required this.collections,
    required this.refunds,
    required this.net,
    required this.appointments,
    required this.admitted,
    required this.lowStock,
  });

  factory TodaySummary.fromServer(
      Map<String, dynamic> report, Map<String, dynamic>? appointments) {
    final fin = (report['finance'] as Map?)?.cast<String, dynamic>() ?? {};
    final ipd = (report['ipd'] as Map?)?.cast<String, dynamic>() ?? {};
    final inv = (report['inventory'] as Map?)?.cast<String, dynamic>() ?? {};
    num n(Object? v) => v is num ? v : num.tryParse('$v') ?? 0;
    return TodaySummary(
      collections: n(fin['revenue']),
      refunds: n(fin['refunds']),
      net: n(fin['net']),
      appointments: appointments == null ? null : n(appointments['total']).toInt(),
      admitted: n(ipd['currently_admitted']).toInt(),
      lowStock: (inv['low_stock'] as List?)?.length ?? 0,
    );
  }

  final num collections;
  final num refunds;
  final num net;
  final int? appointments;
  final int admitted;
  final int lowStock;
}

String _today() {
  final d = DateTime.now();
  return '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';
}

class ReportsCard extends StatefulWidget {
  const ReportsCard({super.key, required this.graph});

  final AppGraph graph;

  @override
  State<ReportsCard> createState() => _ReportsCardState();
}

class _ReportsCardState extends State<ReportsCard> {
  TodaySummary? _summary;
  bool _offline = false;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _offline = false;
    });
    final day = _today();
    try {
      final report = await widget.graph.client.reportSummary(day, day);
      Map<String, dynamic>? appts;
      try {
        appts = await widget.graph.client.listAppointments(day, day, limit: 1);
      } on ApiException {
        appts = null; // no appointment.read: show the rest
      }
      if (!mounted) return;
      setState(() => _summary = TodaySummary.fromServer(report, appts));
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error =
          e.status == 403 ? context.l10n.reportsForbidden : e.detail);
    } catch (_) {
      if (!mounted) return;
      setState(() => _offline = true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    if (_loading) return const LinearProgressIndicator();
    if (_offline) return NeedsConnectionPanel(onRetry: _load);
    if (_error != null) {
      return Text(_error!, key: const Key('reports-error'));
    }
    final s = _summary!;
    String money(num v) => '₹${v.toStringAsFixed(2)}';
    Widget tile(String key, String label, String value) => Card(
          key: Key('report-$key'),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: Theme.of(context).textTheme.labelMedium),
                Text(value, style: Theme.of(context).textTheme.titleLarge),
              ],
            ),
          ),
        );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(children: [
          Expanded(child: Text(l.reportsToday, style: Theme.of(context).textTheme.titleSmall)),
          IconButton(
              tooltip: l.refresh,
              onPressed: _load,
              icon: const Icon(Icons.refresh)),
        ]),
        Wrap(spacing: 8, runSpacing: 8, children: [
          tile('collections', l.reportsCollections, money(s.collections)),
          tile('refunds', l.reportsRefunds, money(s.refunds)),
          tile('net', l.reportsNet, money(s.net)),
          tile('appointments', l.reportsAppointments,
              s.appointments == null ? '—' : '${s.appointments}'),
          tile('admitted', l.reportsAdmitted, '${s.admitted}'),
          tile('low-stock', l.reportsLowStock, '${s.lowStock}'),
        ]),
        Text(l.reportsServerNote, style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}

/// Sync health of this device (works offline).
class SyncHealthCard extends StatelessWidget {
  const SyncHealthCard({super.key, required this.graph});

  final AppGraph graph;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([graph.revision, graph.lastSync, graph.network]),
      builder: (context, _) {
        final l = context.l10n;
        final counts = graph.statusCounts();
        return Card(
          key: const Key('sync-health'),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(l.syncHealthTitle, style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 6),
                Wrap(spacing: 6, runSpacing: 6, children: [
                  SyncStatusChip(status: graph.globalSyncStatus()),
                  for (final s in [
                    SyncStatus.pendingSync,
                    SyncStatus.savedOnDevice,
                    SyncStatus.conflict,
                    SyncStatus.actionRequired,
                  ])
                    SyncStatusChip(
                      status: s,
                      label: l.statusCount(syncStatusLabel(l, s), counts[s] ?? 0),
                    ),
                ]),
              ],
            ),
          ),
        );
      },
    );
  }
}

class OverviewTab extends StatelessWidget {
  const OverviewTab({super.key, required this.graph});

  final AppGraph graph;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        ReportsCard(graph: graph),
        const SizedBox(height: 12),
        SyncHealthCard(graph: graph),
      ],
    );
  }
}

/// Full-screen "Today's summary" for any role (server enforces report.read).
class ReportsScreen extends StatelessWidget {
  const ReportsScreen({super.key, required this.graph});

  final AppGraph graph;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(context.l10n.reportsTitle)),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [ReportsCard(graph: graph)],
        ),
      );
}
