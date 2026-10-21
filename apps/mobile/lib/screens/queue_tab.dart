/// Queue tab: add walk-ins to today's OPD queue. Works offline — the
/// mutation lands in the outbox with a per-day dedupe key, so tapping twice
/// (or retrying after a restart) can never double-book a patient.
///
/// The patient and branch pickers read the persistent [DirectoryCache], so
/// the tab keeps working with no network at all. A patient registered on
/// this device before syncing is referenced as `$ref:<local>` and the sync
/// engine swaps in the server id once the registration is accepted.
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../data/directory.dart';
import '../l10n/l10n.dart';
import '../settings/app_settings.dart';
import '../sync/outbox.dart';
import '../util/dates.dart';
import '../scan/checkin.dart';
import '../scan/scanner.dart';
import 'sync_widgets.dart';

class QueueTab extends StatefulWidget {
  const QueueTab({super.key, required this.graph, this.checkIn = false});

  final AppGraph graph;

  /// Show "Scan check-in QR" (server reported opd_queue + checkin.manage).
  final bool checkIn;

  @override
  State<QueueTab> createState() => _QueueTabState();
}

class _QueueTabState extends State<QueueTab> {
  String? _patientId;
  String? _branchId;
  String? _error;
  String? _notice;
  bool _loading = false;

  DirectoryCache get _directory => widget.graph.directory;

  @override
  void initState() {
    super.initState();
    _patientId = _directory.resolveSelection(null, widget.graph.idMap);
    _branchId = _directory.branches.isNotEmpty
        ? _directory.branches.first['id'] as String?
        : null;
    _refresh();
  }

  List<Map<String, dynamic>>? _today;
  bool _todayOffline = false;

  /// Today's server queue — fetched only when asked (data / battery).
  Future<void> _loadToday() async {
    try {
      final page = await widget.graph.client.listQueue(localDay());
      if (!mounted) return;
      setState(() {
        _today = DirectoryCache.listOf(page['items']);
        _todayOffline = false;
      });
    } catch (_) {
      if (mounted) setState(() => _todayOffline = true);
    }
  }

  /// Scan the desk QR (opaque token, no PHI) → queued check-in request.
  Future<void> _scanCheckIn() async {
    final l = context.l10n;
    final raw =
        await widget.graph.scanner.scan(context, ScanPurpose.checkIn);
    if (raw == null || !mounted) return;
    final token = CheckInToken.parse(raw);
    if (token == null) {
      setState(() {
        _notice = null;
        _error = l.checkInInvalid;
      });
      return;
    }
    final before = widget.graph.outbox.total;
    widget.graph.checkIn.enqueue(token, branchId: _branchId);
    final duplicate = widget.graph.outbox.total == before;
    widget.graph.scheduler.requestSync();
    setState(() {
      _error = null;
      _notice = duplicate ? l.checkInDuplicate : l.checkInSaved;
    });
  }

  /// Best-effort network refresh; the cache already covers the offline case.
  Future<void> _refresh() async {
    setState(() => _loading = true);
    try {
      final patients = await widget.graph.client.listPatients();
      final branches = await widget.graph.client.listBranches();
      final items = DirectoryCache.listOf(patients['items']);
      if (!mounted) return;
      // Merge, never replace: unsynced offline registrations stay (H24).
      await _directory.replacePatients(items, idMap: widget.graph.idMap);
      await _directory.replaceBranches(DirectoryCache.listOf(branches));
      if (!mounted) return;
      setState(() {
        _patientId =
            _directory.resolveSelection(_patientId, widget.graph.idMap);
        _branchId ??= _directory.branches.isNotEmpty
            ? _directory.branches.first['id'] as String?
            : null;
        _error = null;
        _loading = false;
      });
    } catch (_) {
      // Offline: the cached directory still works.
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  /// Server id for a directory entry: resolved id when its registration has
  /// synced, the `$ref:` placeholder otherwise — never a raw device id.
  String _patientRef(String id) => _directory.refFor(id, widget.graph.idMap);

  void _addToQueue() {
    final outbox = widget.graph.outbox;
    final patientId =
        widget.graph.directory.resolveSelection(_patientId, widget.graph.idMap);
    final branchId = _branchId;
    if (patientId == null || branchId == null) {
      setState(() => _error = context.l10n.queuePickBoth);
      return;
    }
    final dedupeKey = 'queue:$patientId:${localDay()}';
    final alreadyQueued = outbox.openOpFor(dedupeKey) != null;
    outbox.enqueue(
      entity: 'queue_entry',
      method: 'POST',
      path: '/opd/queue',
      payload: {
        'patient_id': _patientRef(patientId),
        'branch_id': branchId,
      },
      dedupeKey: dedupeKey,
    );
    widget.graph.scheduler.requestSync();
    setState(() {
      _error = null;
      _notice = alreadyQueued
          ? context.l10n.queueDuplicate
          : context.l10n.queueSaved(outbox.count(OpStatus.pending));
    });
  }

  @override
  Widget build(BuildContext context) {
    final outbox = widget.graph.outbox;
    final l = context.l10n;
    final itemHeight = widget.graph.settings.ruralMode
        ? kRuralTouchTarget + 8
        : kMinInteractiveDimension;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Row(
          children: [
            Expanded(
              child: Text(l.queueTitle,
                  style: Theme.of(context).textTheme.titleMedium),
            ),
            TextButton.icon(
              onPressed: _loading ? null : () => _refresh(),
              icon: const Icon(Icons.refresh, size: 18),
              label: Text(l.refresh),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Text(l.patient, style: Theme.of(context).textTheme.labelLarge),
        DropdownButton<String>(
          key: const Key('queue-patient'),
          isExpanded: true,
          itemHeight: itemHeight,
          value: _directory.resolveSelection(_patientId, widget.graph.idMap),
          hint: const Text('—'),
          items: [
            for (final p in _directory.patients)
              DropdownMenuItem<String>(
                value: p['id'] as String,
                child: Text(_directory.pickerLabel(p, widget.graph.idMap,
                    pendingTag: l.pendingSyncTag, syncedTag: l.syncedTag)),
              ),
          ],
          onChanged: (v) => setState(() => _patientId = v),
        ),
        const SizedBox(height: 12),
        Text(l.branch, style: Theme.of(context).textTheme.labelLarge),
        DropdownButton<String>(
          key: const Key('queue-branch'),
          isExpanded: true,
          itemHeight: itemHeight,
          value: _branchId,
          hint: const Text('—'),
          items: [
            for (final b in _directory.branches)
              DropdownMenuItem<String>(
                value: b['id'] as String,
                child: Text((b['name'] as String?) ?? ''),
              ),
          ],
          onChanged: (v) => setState(() => _branchId = v),
        ),
        const SizedBox(height: 12),
        FilledButton(
          key: const Key('queue-add'),
          onPressed: _addToQueue,
          child: Text(l.queueAdd),
        ),
        if (widget.checkIn)
          OutlinedButton.icon(
            key: const Key('queue-scan-checkin'),
            onPressed: _scanCheckIn,
            icon: const Icon(Icons.qr_code_scanner),
            label: Text(l.checkInScan),
          ),
        const SizedBox(height: 8),
        Text(
          key: const Key('outbox-counts'),
          l.outboxCounts(
            outbox.count(OpStatus.pending),
            outbox.count(OpStatus.failed),
            outbox.count(OpStatus.conflicted),
          ),
          style: Theme.of(context).textTheme.bodySmall,
        ),
        if (_notice != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_notice!, key: const Key('queue-notice')),
          ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              _error!,
              key: const Key('queue-error'),
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        if (_directory.patients.isEmpty && _error == null)
          Padding(
            padding: const EdgeInsets.only(top: 16),
            child: Text(
              _loading ? l.loadingPatients : l.noPatientsCached,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        const SizedBox(height: 16),
        Row(children: [
          Expanded(
            child: Text(l.queueToday,
                style: Theme.of(context).textTheme.titleSmall),
          ),
          TextButton(
            key: const Key('queue-today-load'),
            onPressed: _loadToday,
            child: Text(_today == null ? l.queueTodayShow : l.refresh),
          ),
        ]),
        if (_todayOffline) const NeedsConnectionPanel(),
        if (_today != null && !_todayOffline)
          for (final e in _today!)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: Text('#${e['token_number'] ?? ''}'),
              title: Text(_directory.patientLabel('${e['patient_id']}')),
              subtitle: Text('${e['status'] ?? ''}'),
            ),
      ],
    );
  }
}
