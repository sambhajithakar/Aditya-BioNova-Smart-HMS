/// Sync tab: the sync centre.
///
/// Shows every queued mutation with its **explicit sync state** (R4.2:
/// Saved on device · Pending sync / Synced / Conflict, plus retryable
/// failures with their automatic retry time), runs a push, and resolves
/// conflicts one by one. Nothing is ever dropped silently and nothing is
/// last-write-wins:
/// * duplicate registration (409 with candidates) → "Register anyway"
///   re-sends with `allow_duplicates: true` after an explicit confirmation
///   (D8), or Discard;
/// * created by another user → never sent under this account; a legacy op
///   with no recorded creator can be claimed explicitly;
/// * discarding a registration also discards every queued change that
///   depends on it, and says so first (D9).
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../l10n/l10n.dart';
import '../sync/outbox.dart';
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
  }

  @override
  void dispose() {
    graph.revision.removeListener(_changed);
    graph.lastSync.removeListener(_changed);
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
      await graph.drafts.adoptSynced(graph.idMap);
      graph.lastSync.value = result;
      if (result.stoppedUnauthorized) graph.sessionExpired.value = true;
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

  Future<void> _registerAnyway(OutboxOp op) async {
    final l = context.l10n;
    final name = '${op.payload['full_name'] ?? l.thisPatient}';
    final ok = await _confirm(
      title: l.registerAnywayTitle,
      body: l.registerAnywayBody(name),
      action: l.registerAnywayAction,
    );
    if (!ok) return;
    graph.outbox.reissue(op, {...op.payload, 'allow_duplicates': true});
    if (!mounted) return;
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
    final outbox = graph.outbox;
    final dependents = outbox.dependentsOf(op);
    final l = context.l10n;
    final entity = entityLabel(l, op.entity);
    if (dependents.isNotEmpty) {
      final what = dependents.map((d) => entityLabel(l, d.entity)).join(', ');
      final ok = await _confirm(
        title: l.discardTitle(entity, dependents.length),
        body: l.discardBody(dependents.length, what, entity),
        action: l.discardAll,
        destructive: true,
      );
      if (!ok) return;
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
    await graph.drafts.markDiscarded([
      for (final r in removed)
        if (r.entity == 'prescription' && r.localRef != null) r.localRef!,
    ]);
    if (!mounted) return;
    setState(() => _notice = dependents.isEmpty
        ? l.discardedOne(entity)
        : l.discardedMany(entity, dependents.length));
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
    return [
      TextButton(
        key: Key('conflict-keep-${op.id}'),
        onPressed: () {
          graph.outbox.resolveConflict(op, keepLocal: true);
          setState(() {});
        },
        child: Text(l.conflictKeep),
      ),
      discard,
    ];
  }

  @override
  Widget build(BuildContext context) {
    final outbox = graph.outbox;
    final result = graph.lastSync.value;
    final conflicted =
        outbox.ops.where((o) => o.status == OpStatus.conflicted).toList();
    final nextRetry = outbox.nextRetryAt;
    final l = context.l10n;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(l.syncTitle, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
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
                  (result.deferred > 0 ? l.syncWaiting(result.deferred) : '') +
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
                for (final entity in result.synced)
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
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                ),
        ),
        const SizedBox(height: 16),
        Text(l.syncQueued, style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 4),
        for (final op in outbox.ops)
          Card(
            margin: const EdgeInsets.symmetric(vertical: 6),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${entityLabel(l, op.entity)} · ${op.method} ${op.path}',
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                  const SizedBox(height: 6),
                  OpStateChip(op: op),
                  if (op.lastError.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(
                        op.lastError,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                ],
              ),
            ),
          ),
        if (outbox.ops.isEmpty)
          Text(
            l.syncNothingQueued,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        const SizedBox(height: 16),
        if (conflicted.isEmpty)
          Text(
            l.syncNoConflicts,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        for (final op in conflicted)
          Card(
            margin: const EdgeInsets.symmetric(vertical: 6),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${entityLabel(l, op.entity)} · ${op.method} ${op.path}',
                      style: Theme.of(context).textTheme.titleSmall),
                  Text(op.lastError,
                      style: Theme.of(context).textTheme.bodySmall),
                  const SizedBox(height: 8),
                  Wrap(children: _resolutions(op)),
                ],
              ),
            ),
          ),
      ],
    );
  }
}
