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
import '../sync/conflict.dart';
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
            child: const Text('Cancel'),
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
    final name = op.payload['full_name'] ?? 'this patient';
    final ok = await _confirm(
      title: 'Register as a NEW patient?',
      body: 'The server found existing patient(s) that look like $name. '
          'Only continue if you have checked this is a different person — '
          'a duplicate record splits the patient\'s history.',
      action: 'Register anyway',
    );
    if (!ok) return;
    graph.outbox.reissue(op, {...op.payload, 'allow_duplicates': true});
    setState(() => _notice = 'Will register $name as a new patient on the '
        'next sync.');
  }

  Future<void> _claim(OutboxOp op) async {
    final me = (await graph.session.profile())?.userId;
    if (me == null || !mounted) return;
    final ok = await _confirm(
      title: 'Send under your account?',
      body: 'This change was saved before the app recorded who made it. '
          'Send it only if you made it.',
      action: 'Send as me',
    );
    if (!ok) return;
    op.userId = me;
    graph.outbox.resolveConflict(op, keepLocal: true);
    setState(() {});
  }

  Future<void> _discard(OutboxOp op) async {
    final outbox = graph.outbox;
    final dependents = outbox.dependentsOf(op);
    if (dependents.isNotEmpty) {
      final what = dependents.map((d) => d.entity.replaceAll('_', ' ')).join(', ');
      final ok = await _confirm(
        title: 'Discard ${op.entity} and ${dependents.length} more?',
        body: '${dependents.length} queued change'
            '${dependents.length == 1 ? '' : 's'} ($what) '
            'refer${dependents.length == 1 ? 's' : ''} to this '
            '${op.entity} and can never be sent without it. '
            'They will be discarded too.',
        action: 'Discard all',
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
        ? 'Discarded: ${op.entity}.'
        : 'Discarded: ${op.entity} and ${dependents.length} dependent '
            'change${dependents.length == 1 ? '' : 's'}.');
  }

  String _when(DateTime at) {
    final local = at.toLocal();
    String two(int v) => v.toString().padLeft(2, '0');
    return '${two(local.hour)}:${two(local.minute)}:${two(local.second)}';
  }

  List<Widget> _resolutions(OutboxOp op) {
    final reason = op.conflictReason;
    final discard = TextButton(
      key: Key('conflict-discard-${op.id}'),
      onPressed: () => _discard(op),
      child: const Text('Discard (server wins here)'),
    );
    if (reason == ConflictReason.duplicatePatient) {
      return [
        TextButton(
          key: Key('conflict-register-anyway-${op.id}'),
          onPressed: () => _registerAnyway(op),
          child: const Text('Keep local (register anyway)'),
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
            child: const Text('Keep local (send as me)'),
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
        child: const Text('Keep local (re-send)'),
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

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Sync centre', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Text(
          key: const Key('sync-counts'),
          'pending: ${outbox.count(OpStatus.pending)} · '
          'failed: ${outbox.count(OpStatus.failed)} · '
          'conflicted: ${outbox.count(OpStatus.conflicted)}',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        if (nextRetry != null)
          Text(
            key: const Key('sync-next-retry'),
            'Automatic retry from ${_when(nextRetry)}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        const SizedBox(height: 12),
        Row(
          children: [
            FilledButton(
              key: const Key('sync-run'),
              onPressed: _busy ? null : () => _sync(),
              child: Text(_busy ? 'Syncing…' : 'Sync now'),
            ),
            const SizedBox(width: 8),
            OutlinedButton(
              key: const Key('sync-retry'),
              onPressed:
                  outbox.count(OpStatus.failed) == 0 ? null : _retryFailed,
              child: const Text('Retry failed now'),
            ),
          ],
        ),
        if (result != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              key: const Key('sync-result'),
              'pushed ${result.pushed} · conflicts '
              '${result.conflicts.length} · failed ${result.failed}'
              '${result.deferred > 0 ? ' · waiting ${result.deferred}' : ''}'
              '${result.stoppedUnauthorized ? ' · stopped (sign in again)' : ''}',
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
                    label: 'Synced · $entity',
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
                    'Could not save to device storage: $err',
                    key: const Key('sync-persist-error'),
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                ),
        ),
        const SizedBox(height: 16),
        Text('Queued on this device',
            style: Theme.of(context).textTheme.titleSmall),
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
                    '${op.entity} · ${op.method} ${op.path}',
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
            'Nothing queued — every change has reached the server.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        const SizedBox(height: 16),
        if (conflicted.isEmpty)
          Text(
            'No conflicts — local and server agree.',
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
                  Text('${op.entity} · ${op.method} ${op.path}',
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

/// Exported so the shell can classify conflict kinds for tooltips.
String conflictLabel(ConflictKind kind) => switch (kind) {
      ConflictKind.versionMismatch => 'The record changed on the server',
      ConflictKind.rejectedByPolicy => 'The server refused this change',
      ConflictKind.authRequired => 'Sign in again to continue',
      ConflictKind.duplicatePatient => 'Possible duplicate registration',
      ConflictKind.wrongUser => 'Created by another user on this device',
    };
