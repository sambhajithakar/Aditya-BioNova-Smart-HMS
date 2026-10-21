/// Sync tab: the sync dashboard.
///
/// * counts per status (Saved on device / Pending sync / Syncing / Conflict
///   / Action required) and the global status;
/// * "Sync now", "Retry failed", and per-item "Retry now";
/// * every queued item with its status chip and the last error in plain
///   words; tap an item for its details (idempotency key, attempts,
///   dependency, server answer);
/// * conflicts and action-required items FIRST, each with an explicit
///   resolution — nothing is ever dropped silently and nothing is
///   last-write-wins:
///   - duplicate registration (409 with candidates) → review screen: keep
///     mine as a NEW patient (`allow_duplicates: true`, new key, confirmed
///     — D8), use the server record (dependants re-pointed to it), or
///     merge by review (field by field, online), or Discard;
///   - version mismatch → review: send mine again (new key, confirmed) or
///     use the server version (discard mine);
///   - created by another user → never sent under this account; a legacy
///     op with no recorded creator can be claimed explicitly;
///   - refused by the server / tried too often → Retry now, or Discard;
///   - discarding a registration also discards every queued change that
///     depends on it, and says so first (D9);
/// * storage used on the device + "Clear cached patient data";
/// * a sealed quarantine left by a signed-out user: count only, explicit
///   discard.
///
/// The item list is a lazy `SliverList` (thousands of items stay cheap).
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../l10n/l10n.dart';
import '../sync/outbox.dart';
import '../sync/planner.dart';
import '../sync/sync_status.dart';
import 'conflict_screen.dart';
import 'op_detail_screen.dart';
import 'sync_widgets.dart';
import 'widgets.dart';

class SyncTab extends StatefulWidget {
  const SyncTab({super.key, required this.graph});

  final AppGraph graph;

  @override
  State<SyncTab> createState() => _SyncTabState();
}

class _SyncTabState extends State<SyncTab> {
  String? _error;
  String? _notice;
  bool _busy = false;

  AppGraph get graph => widget.graph;

  @override
  void initState() {
    super.initState();
    graph.revision.addListener(_changed);
    graph.lastSync.addListener(_changed);
    graph.network.addListener(_changed);
  }

  @override
  void dispose() {
    graph.revision.removeListener(_changed);
    graph.lastSync.removeListener(_changed);
    graph.network.removeListener(_changed);
    super.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  Future<void> _sync() async {
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      final result = await graph.engine.sync();
      await graph.adoptSynced();
      graph.lastSync.value = result;
      if (result.stoppedUnauthorized && !graph.deviceRevoked.value) {
        graph.sessionExpired.value = true;
      }
    } catch (err) {
      if (!mounted) return;
      setState(() => _error = err.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _retryFailed() {
    graph.outbox.retryOpen();
    setState(() {});
  }

  Future<bool> _confirm({
    required String title,
    required String body,
    required String action,
    bool destructive = false,
  }) =>
      confirmDialog(context,
          title: title, body: body, action: action, destructive: destructive);

  Future<void> _registerAnyway(OutboxOp op) async {
    final name = await registerAnyway(context, graph, op);
    if (name == null || !mounted) return;
    setState(() => _notice = context.l10n.registerAnywayNotice(name));
  }

  Future<void> _claim(OutboxOp op) async {
    final me = (await graph.session.profile())?.userId;
    if (me == null || !mounted) return;
    final l = context.l10n;
    final ok = await _confirm(
      title: l.claimTitle,
      body: l.claimBody,
      action: l.claimAction,
    );
    if (!ok) return;
    op.userId = me;
    graph.outbox.resolveConflict(op, keepLocal: true);
    setState(() {});
  }

  Future<void> _discard(OutboxOp op) async {
    final message = await discardOp(context, graph, op);
    if (message == null || !mounted) return;
    setState(() => _notice = message);
  }

  Future<void> _sendMineAgain(OutboxOp op) async {
    final l = context.l10n;
    final ok = await _confirm(
      title: l.conflictSendMineTitle,
      body: l.conflictSendMineBody,
      action: l.conflictSendMine,
    );
    if (!ok) return;
    graph.outbox.reissue(op, Map<String, dynamic>.of(op.payload));
    setState(() {});
  }

  Future<void> _review(OutboxOp op) async {
    final message = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(
        builder: (_) => ConflictScreen(graph: graph, op: op),
      ),
    );
    if (!mounted) return;
    setState(() => _notice = message ?? _notice);
  }

  Future<void> _openDetail(OutboxOp op) async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => OpDetailScreen(graph: graph, op: op),
      ),
    );
    if (mounted) setState(() {});
  }

  Future<void> _clearPatientCache() async {
    final l = context.l10n;
    final ok = await _confirm(
      title: l.clearCacheTitle,
      body: l.clearCacheBody,
      action: l.clearCacheAction,
    );
    if (!ok) return;
    final n = await graph.directory.clearCachedPatients();
    if (!mounted) return;
    setState(() => _notice = context.l10n.clearCacheDone(n));
  }

  Future<void> _discardQuarantine() async {
    final l = context.l10n;
    final n = graph.quarantine.info?.items ?? 0;
    final ok = await _confirm(
      title: l.quarantineDiscardTitle(n),
      body: l.quarantineDiscardBody,
      action: l.quarantineDiscardAction,
      destructive: true,
    );
    if (!ok) return;
    await graph.discardQuarantine();
    if (!mounted) return;
    setState(() => _notice = context.l10n.quarantineDiscarded);
  }

  String _when(DateTime at) {
    final local = at.toLocal();
    String two(int v) => v.toString().padLeft(2, '0');
    return '${two(local.hour)}:${two(local.minute)}:${two(local.second)}';
  }

  List<Widget> _resolutions(OutboxOp op) {
    final reason = op.conflictReason;
    final l = context.l10n;
    final discard = TextButton(
      key: Key('conflict-discard-${op.id}'),
      onPressed: () => _discard(op),
      child: Text(l.conflictDiscard),
    );
    if (reason == ConflictReason.duplicatePatient) {
      return [
        TextButton(
          key: Key('conflict-review-${op.id}'),
          onPressed: () => _review(op),
          child: Text(l.conflictReview),
        ),
        TextButton(
          key: Key('conflict-register-anyway-${op.id}'),
          onPressed: () => _registerAnyway(op),
          child: Text(l.conflictRegisterAnyway),
        ),
        discard,
      ];
    }
    if (reason == ConflictReason.wrongUser) {
      return [
        if (op.userId == null)
          TextButton(
            key: Key('conflict-claim-${op.id}'),
            onPressed: () => _claim(op),
            child: Text(l.conflictClaim),
          ),
        discard,
      ];
    }
    if (reason == ConflictReason.versionMismatch) {
      return [
        TextButton(
          key: Key('conflict-review-${op.id}'),
          onPressed: () => _review(op),
          child: Text(l.conflictReview),
        ),
        TextButton(
          key: Key('conflict-keep-${op.id}'),
          onPressed: () => _sendMineAgain(op),
          child: Text(l.conflictSendMine),
        ),
        discard,
      ];
    }
    if (reason == ConflictReason.orphaned) return [discard];
    // refused by the server / too many attempts
    return [
      TextButton(
        key: Key('conflict-retry-${op.id}'),
        onPressed: () {
          graph.outbox.retryNow(op);
          setState(() {});
        },
        child: Text(l.retryNow),
      ),
      discard,
    ];
  }

  Widget _countChips(Map<SyncStatus, int> counts) {
    final l = context.l10n;
    const shown = [
      SyncStatus.savedOnDevice,
      SyncStatus.pendingSync,
      SyncStatus.syncing,
      SyncStatus.conflict,
      SyncStatus.actionRequired,
    ];
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        for (final s in shown)
          SyncStatusChip(
            key: Key('status-count-${s.name}'),
            status: s,
            label: l.statusCount(syncStatusLabel(l, s), counts[s] ?? 0),
          ),
      ],
    );
  }

  Widget _header(BuildContext context, SyncPlanner planner,
      Map<SyncStatus, int> counts) {
    final outbox = graph.outbox;
    final result = graph.lastSync.value;
    final nextRetry = outbox.nextRetryAt;
    final l = context.l10n;
    final attention = [
      for (final op in outbox.ops)
        if (op.status == OpStatus.conflicted) op,
    ];
    final blocked = [
      for (final op in outbox.ops)
        if (op.status != OpStatus.conflicted &&
            planner.infoFor(op).state == DependencyState.blocked)
          op,
    ];
    final q = graph.quarantine.info;
    final usage = graph.storageUsage();
    final totalKb =
        (usage.values.fold<int>(0, (a, b) => a + b) / 1024).ceil();

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text(l.syncTitle,
                  style: Theme.of(context).textTheme.titleMedium),
            ),
            SyncStatusChip(
              key: const Key('sync-global-status'),
              status: graph.globalSyncStatus(),
            ),
          ]),
          const SizedBox(height: 8),
          _countChips(counts),
          const SizedBox(height: 6),
          Text(
            key: const Key('sync-counts'),
            l.syncCounts(
              outbox.count(OpStatus.pending),
              outbox.count(OpStatus.failed),
              outbox.count(OpStatus.conflicted),
            ),
            style: Theme.of(context).textTheme.bodySmall,
          ),
          if (nextRetry != null)
            Text(
              key: const Key('sync-next-retry'),
              l.syncNextRetry(_when(nextRetry)),
              style: Theme.of(context).textTheme.bodySmall,
            ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              FilledButton(
                key: const Key('sync-run'),
                onPressed: _busy ? null : () => _sync(),
                child: Text(_busy ? l.opSyncing : l.syncNow),
              ),
              OutlinedButton(
                key: const Key('sync-retry'),
                onPressed:
                    outbox.count(OpStatus.failed) == 0 ? null : _retryFailed,
                child: Text(l.syncRetryFailed),
              ),
            ],
          ),
          if (result != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                key: const Key('sync-result'),
                l.syncResult(
                      result.pushed,
                      result.conflicts.length,
                      result.failed,
                    ) +
                    (result.deferred > 0
                        ? l.syncWaiting(result.deferred)
                        : '') +
                    (result.stoppedUnauthorized ? l.syncStopped : ''),
              ),
            ),
          if (result != null && result.synced.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Wrap(
                spacing: 6,
                runSpacing: 4,
                children: [
                  for (final entity in result.synced.toSet())
                    StateChip(
                      key: Key('synced-$entity'),
                      label: l.syncedEntity(entityLabel(l, entity)),
                      tone: const Color(0xFF1B7F5A),
                    ),
                ],
              ),
            ),
          if (_notice != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_notice!, key: const Key('sync-notice')),
            ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          ValueListenableBuilder<String?>(
            valueListenable: graph.persistError,
            builder: (context, err, _) => err == null
                ? const SizedBox.shrink()
                : Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      context.l10n.syncPersistError(err),
                      key: const Key('sync-persist-error'),
                      style: TextStyle(
                          color: Theme.of(context).colorScheme.error),
                    ),
                  ),
          ),
          if (q != null)
            Card(
              key: const Key('quarantine-card'),
              margin: const EdgeInsets.only(top: 12),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(l.quarantineTitle(q.items),
                        style: Theme.of(context).textTheme.titleSmall),
                    Text(l.quarantineBody,
                        style: Theme.of(context).textTheme.bodySmall),
                    TextButton(
                      key: const Key('quarantine-discard'),
                      onPressed: _discardQuarantine,
                      child: Text(l.quarantineDiscardAction),
                    ),
                  ],
                ),
              ),
            ),
          const SizedBox(height: 16),
          Text(l.syncAttention, style: Theme.of(context).textTheme.titleSmall),
          if (attention.isEmpty && blocked.isEmpty)
            Text(
              l.syncNoConflicts,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          for (final op in attention)
            Card(
              key: Key('conflict-card-${op.id}'),
              margin: const EdgeInsets.symmetric(vertical: 6),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Expanded(
                        child: Text(
                            '${entityLabel(l, op.entity)} · ${op.method} ${op.path}',
                            style: Theme.of(context).textTheme.titleSmall),
                      ),
                      SyncStatusChip(
                          status: statusOfOp(op,
                              network: graph.network.value,
                              dependency: planner.infoFor(op))),
                    ]),
                    Text(humanError(l, op),
                        style: Theme.of(context).textTheme.bodySmall),
                    const SizedBox(height: 8),
                    Wrap(children: _resolutions(op)),
                  ],
                ),
              ),
            ),
          for (final op in blocked)
            ListTile(
              key: Key('blocked-${op.id}'),
              contentPadding: EdgeInsets.zero,
              dense: true,
              leading: const Icon(Icons.link_off),
              title: Text(entityLabel(l, op.entity)),
              subtitle: Text(l.blockedBy(entityLabel(
                  l, planner.infoFor(op).parent?.entity ?? ''))),
              onTap: () => _openDetail(op),
            ),
          const SizedBox(height: 12),
          Card(
            key: const Key('storage-card'),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(l.storageTitle,
                      style: Theme.of(context).textTheme.titleSmall),
                  Text(
                    l.storageUsage(totalKb, graph.directory.cachedServerPatients,
                        outbox.total),
                    key: const Key('storage-usage'),
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  TextButton(
                    key: const Key('clear-patient-cache'),
                    onPressed: graph.directory.cachedServerPatients == 0
                        ? null
                        : _clearPatientCache,
                    child: Text(l.clearCacheAction),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text(l.syncQueued, style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 4),
          if (outbox.ops.isEmpty)
            Text(
              l.syncNothingQueued,
              style: Theme.of(context).textTheme.bodySmall,
            ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final outbox = graph.outbox;
    final planner = SyncPlanner(outbox.ops, graph.idMap);
    final counts = countByStatus(outbox, planner, network: graph.network.value);
    final ops = outbox.ops;
    final l = context.l10n;

    return CustomScrollView(
      key: const Key('sync-dashboard'),
      slivers: [
        SliverToBoxAdapter(child: _header(context, planner, counts)),
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          sliver: SliverList.builder(
            itemCount: ops.length,
            itemBuilder: (context, i) {
              final op = ops[i];
              final status = statusOfOp(op,
                  network: graph.network.value,
                  dependency: planner.infoFor(op));
              final err = humanError(l, op);
              final canRetry = op.status == OpStatus.failed ||
                  op.conflictReason == ConflictReason.maxAttempts ||
                  op.conflictReason == ConflictReason.rejectedByPolicy;
              return Card(
                key: Key('op-tile-${op.id}'),
                margin: const EdgeInsets.symmetric(vertical: 4),
                child: ListTile(
                  onTap: () => _openDetail(op),
                  title: Text(
                    '${entityLabel(l, op.entity)} · ${op.method} ${op.path}',
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                  subtitle: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const SizedBox(height: 4),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: SyncStatusChip(status: status),
                      ),
                      Text(opStateLabel(l, op),
                          style: Theme.of(context).textTheme.bodySmall),
                      if (err.isNotEmpty)
                        Text(err,
                            style: Theme.of(context).textTheme.bodySmall),
                    ],
                  ),
                  trailing: canRetry
                      ? IconButton(
                          key: Key('op-retry-${op.id}'),
                          tooltip: l.retryNow,
                          icon: const Icon(Icons.refresh),
                          onPressed: () {
                            graph.outbox.retryNow(op);
                            setState(() {});
                          },
                        )
                      : null,
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}

/// Shared confirmation dialog (keys `confirm-ok` / `confirm-cancel`).
Future<bool> confirmDialog(
  BuildContext context, {
  required String title,
  required String body,
  required String action,
  bool destructive = false,
}) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: Text(body),
      actions: [
        TextButton(
          key: const Key('confirm-cancel'),
          onPressed: () => Navigator.of(ctx).pop(false),
          child: Text(ctx.l10n.cancel),
        ),
        FilledButton(
          key: const Key('confirm-ok'),
          style: destructive
              ? FilledButton.styleFrom(
                  backgroundColor: Theme.of(ctx).colorScheme.error)
              : null,
          onPressed: () => Navigator.of(ctx).pop(true),
          child: Text(action),
        ),
      ],
    ),
  );
  return ok == true;
}

/// "Keep mine as a NEW patient": confirmed re-send with
/// `allow_duplicates: true` under a NEW idempotency key (D8). Returns the
/// patient's name, or null when cancelled.
Future<String?> registerAnyway(
    BuildContext context, AppGraph graph, OutboxOp op) async {
  final l = context.l10n;
  final name = '${op.payload['full_name'] ?? l.thisPatient}';
  final ok = await confirmDialog(
    context,
    title: l.registerAnywayTitle,
    body: l.registerAnywayBody(name),
    action: l.registerAnywayAction,
  );
  if (!ok) return null;
  graph.outbox.reissue(op, {...op.payload, 'allow_duplicates': true});
  return name;
}

/// Discard [op] (and, after an explicit warning, everything depending on
/// it). Returns the notice to show, or null when cancelled.
Future<String?> discardOp(
    BuildContext context, AppGraph graph, OutboxOp op) async {
  final outbox = graph.outbox;
  final dependents = outbox.dependentsOf(op);
  final l = context.l10n;
  final entity = entityLabel(l, op.entity);
  if (dependents.isNotEmpty) {
    final what = dependents.map((d) => entityLabel(l, d.entity)).join(', ');
    final ok = await confirmDialog(
      context,
      title: l.discardTitle(entity, dependents.length),
      body: l.discardBody(dependents.length, what, entity),
      action: l.discardAll,
      destructive: true,
    );
    if (!ok) return null;
  }
  final removed = [op, ...dependents];
  if (op.status == OpStatus.conflicted) {
    outbox.resolveConflict(op, keepLocal: false);
  } else {
    outbox.discardWithDependents(op);
  }
  for (final r in removed) {
    final ref = r.localRef;
    if (ref == null) continue;
    if (r.entity == 'patient') await graph.directory.removeLocalPatient(ref);
  }
  final refs = [
    for (final r in removed)
      if (r.localRef != null) r.localRef!,
  ];
  await graph.drafts.markDiscarded(refs);
  await graph.consults.markDiscarded(refs);
  await graph.appointments.markDiscarded(refs);
  return dependents.isEmpty
      ? l.discardedOne(entity)
      : l.discardedMany(entity, dependents.length);
}
