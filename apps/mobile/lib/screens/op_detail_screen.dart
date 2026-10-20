/// Details of one queued change: status, what it waits for, the last error
/// in plain words, attempts, and its idempotency key (for support: the
/// same key is sent on every retry, so the server applies it once).
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../l10n/l10n.dart';
import '../sync/outbox.dart';
import '../sync/planner.dart';
import '../sync/sync_status.dart';
import 'conflict_screen.dart';
import 'sync_tab.dart' show discardOp;
import 'sync_widgets.dart';
import 'widgets.dart';

class OpDetailScreen extends StatefulWidget {
  const OpDetailScreen({super.key, required this.graph, required this.op});

  final AppGraph graph;
  final OutboxOp op;

  @override
  State<OpDetailScreen> createState() => _OpDetailScreenState();
}

class _OpDetailScreenState extends State<OpDetailScreen> {
  AppGraph get graph => widget.graph;
  OutboxOp get op => widget.op;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final planner = SyncPlanner(graph.outbox.ops, graph.idMap);
    final dep = planner.infoFor(op);
    final status =
        statusOfOp(op, network: graph.network.value, dependency: dep);
    final err = humanError(l, op);
    final queued = graph.outbox.byId(op.id) != null;
    final canRetry = op.status == OpStatus.failed ||
        op.conflictReason == ConflictReason.maxAttempts ||
        op.conflictReason == ConflictReason.rejectedByPolicy;
    final reviewable =
        ConflictReason.dataConflicts.contains(op.conflictReason);

    Widget row(String k, String v) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 3),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            SizedBox(
                width: 130,
                child: Text(k, style: Theme.of(context).textTheme.labelMedium)),
            Expanded(child: SelectableText(v)),
          ]),
        );

    return Scaffold(
      appBar: AppBar(title: Text(entityLabel(l, op.entity))),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: SyncStatusChip(key: const Key('detail-status'), status: status),
          ),
          const SizedBox(height: 8),
          if (!queued) Text(l.detailNoLongerQueued),
          row(l.detailRequest, '${op.method} ${op.path}'),
          row(l.detailState, opStateLabel(l, op)),
          row(l.detailCreated, op.createdAt.toLocal().toString()),
          row(l.detailAttempts, '${op.attempts} / ${Outbox.maxAttempts}'),
          if (op.nextAttemptAt != null)
            row(l.detailNextRetry, op.nextAttemptAt!.toLocal().toString()),
          row(l.detailKey, op.id),
          if (op.lastHttpStatus != null)
            row(l.detailHttp, '${op.lastHttpStatus}'),
          if (err.isNotEmpty) row(l.detailError, err),
          if (dep.state == DependencyState.waiting)
            row(l.detailDepends,
                l.waitingFor(entityLabel(l, dep.parent?.entity ?? ''))),
          if (dep.state == DependencyState.blocked)
            row(l.detailDepends,
                l.blockedBy(entityLabel(l, dep.parent?.entity ?? ''))),
          if (dep.state == DependencyState.orphaned)
            row(l.detailDepends, l.orphanedExplain),
          const SizedBox(height: 16),
          if (queued)
            Wrap(spacing: 8, runSpacing: 8, children: [
              if (canRetry)
                FilledButton(
                  key: const Key('detail-retry'),
                  onPressed: () {
                    graph.outbox.retryNow(op);
                    graph.scheduler.requestSync();
                    setState(() {});
                  },
                  child: Text(l.retryNow),
                ),
              if (reviewable)
                FilledButton(
                  key: const Key('detail-review'),
                  onPressed: () async {
                    final msg = await Navigator.of(context).push<String>(
                        MaterialPageRoute<String>(
                            builder: (_) =>
                                ConflictScreen(graph: graph, op: op)));
                    if (msg != null && context.mounted) {
                      Navigator.of(context).pop();
                    }
                  },
                  child: Text(l.conflictReview),
                ),
              OutlinedButton(
                key: const Key('detail-discard'),
                onPressed: () async {
                  final msg = await discardOp(context, graph, op);
                  if (msg != null && context.mounted) {
                    Navigator.of(context).pop();
                  }
                },
                child: Text(l.conflictDiscard),
              ),
            ]),
        ],
      ),
    );
  }
}
