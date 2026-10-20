/// Dependency planning for the outbox (pure Dart, no I/O).
///
/// An op depends on every local ref it mentions — `$ref:<localRef>` in its
/// path or payload, plus explicit [OutboxOp.dependsOn] — that the [IdMap]
/// cannot resolve yet. The op that CREATES that ref is its parent.
///
/// * **ready**    — every parent has synced (refs resolve): push it;
/// * **waiting**  — a parent is still queued (pending / failed / syncing):
///   the child stays **Pending sync** and is pushed right after the parent
///   in the same run, its `$ref:` rewritten to the server id;
/// * **blocked**  — a parent (or grand-parent …) is parked as a Conflict /
///   Action required: the child is NOT attempted and shows **Action
///   required — waiting for the parent** until the parent is resolved;
/// * **orphaned** — the parent is gone (discarded) and the ref never
///   resolved: the child can never be sent as-is → Action required.
///
/// [order] sorts a run topologically — parents before children — and is
/// otherwise stable (queue order), so unrelated ops keep FIFO order.
library;

import 'idmap.dart';
import 'outbox.dart';

enum DependencyState { ready, waiting, blocked, orphaned }

class DependencyInfo {
  const DependencyInfo(this.state, {this.parent, this.missingRef});

  static const DependencyInfo ready = DependencyInfo(DependencyState.ready);

  final DependencyState state;

  /// The nearest parent op responsible for [state] (null for ready /
  /// orphaned).
  final OutboxOp? parent;

  /// The unresolved local ref (orphaned / waiting / blocked).
  final String? missingRef;

  bool get isReady => state == DependencyState.ready;
}

class SyncPlanner {
  SyncPlanner(Iterable<OutboxOp> ops, this.idMap) {
    for (final op in ops) {
      final ref = op.localRef;
      if (ref != null) _creators[ref] = op;
    }
  }

  final IdMap idMap;
  final Map<String, OutboxOp> _creators = {};

  /// The op that creates [localRef], if it is queued.
  OutboxOp? creatorOf(String localRef) => _creators[localRef];

  /// Dependency state of [op] from the CURRENT op statuses (safe to call
  /// again after earlier ops in the run changed state).
  DependencyInfo infoFor(OutboxOp op) => _info(op, <OutboxOp>{});

  DependencyInfo _info(OutboxOp op, Set<OutboxOp> visiting) {
    if (!visiting.add(op)) {
      // A cycle can only come from corrupt data; never push it.
      return DependencyInfo(DependencyState.blocked, parent: op);
    }
    var worst = DependencyInfo.ready;
    for (final ref in op.parentRefs) {
      if (idMap.serverIdOf(ref) != null) continue;
      final parent = _creators[ref];
      final DependencyInfo here;
      if (parent == null || identical(parent, op)) {
        here = DependencyInfo(DependencyState.orphaned, missingRef: ref);
      } else if (parent.status == OpStatus.conflicted) {
        here = DependencyInfo(DependencyState.blocked,
            parent: parent, missingRef: ref);
      } else {
        final up = _info(parent, visiting);
        here = switch (up.state) {
          DependencyState.ready || DependencyState.waiting => DependencyInfo(
              DependencyState.waiting,
              parent: parent,
              missingRef: ref),
          DependencyState.blocked || DependencyState.orphaned =>
            DependencyInfo(DependencyState.blocked,
                parent: up.parent ?? parent, missingRef: ref),
        };
      }
      if (here.state.index > worst.state.index) worst = here;
    }
    visiting.remove(op);
    return worst;
  }

  /// Topological, otherwise-stable order of [eligible]: every parent that
  /// is itself in [eligible] comes before its children.
  List<OutboxOp> order(List<OutboxOp> eligible) {
    final inRun = eligible.toSet();
    final out = <OutboxOp>[];
    final done = <OutboxOp>{};
    final onStack = <OutboxOp>{};

    void visit(OutboxOp root) {
      // Iterative DFS (deep chains must not overflow the stack).
      final stack = <(OutboxOp, int)>[(root, 0)];
      onStack.add(root);
      while (stack.isNotEmpty) {
        final (op, i) = stack.removeLast();
        final refs = op.parentRefs;
        if (i < refs.length) {
          stack.add((op, i + 1));
          final parent = _creators[refs[i]];
          if (parent != null &&
              inRun.contains(parent) &&
              !done.contains(parent) &&
              !onStack.contains(parent)) {
            onStack.add(parent);
            stack.add((parent, 0));
          }
          continue;
        }
        onStack.remove(op);
        if (done.add(op)) out.add(op);
      }
    }

    for (final op in eligible) {
      if (!done.contains(op)) visit(op);
    }
    return out;
  }
}
