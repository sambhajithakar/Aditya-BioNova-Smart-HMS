/// One sync-status vocabulary for the whole app (per record and global):
///
/// | Status            | Per record                                             | Global                               |
/// |-------------------|--------------------------------------------------------|--------------------------------------|
/// | online            | —                                                      | API reachable, nothing queued        |
/// | offline           | —                                                      | API unreachable                      |
/// | savedOnDevice     | queued, device offline (or never tried yet)            | —                                    |
/// | pendingSync       | queued, waiting for a run / backoff / its parent       | something queued, online             |
/// | syncing           | being pushed now                                       | a run is in progress                 |
/// | synced            | accepted by the server                                 | last run clean, queue empty          |
/// | conflict          | server holds a different truth (409/412, duplicate)    | at least one conflict                |
/// | actionRequired    | refused, wrong user, orphaned, max attempts, or        | at least one item needs the user     |
/// |                   | blocked by a parent that needs action                  |                                      |
///
/// Pure functions — the widgets in `screens/sync_widgets.dart` only render
/// what [statusOfOp] / [globalStatus] return.
library;

import 'network.dart';
import 'outbox.dart';
import 'planner.dart';

enum SyncStatus {
  online,
  offline,
  savedOnDevice,
  pendingSync,
  syncing,
  synced,
  conflict,
  actionRequired,
}

/// Status of one queued op. [dependency] is the planner's view of its
/// parents (pass null when unknown).
SyncStatus statusOfOp(
  OutboxOp op, {
  required NetworkState network,
  DependencyInfo? dependency,
}) {
  switch (op.status) {
    case OpStatus.inFlight:
      return SyncStatus.syncing;
    case OpStatus.conflicted:
      return ConflictReason.dataConflicts.contains(op.conflictReason)
          ? SyncStatus.conflict
          : SyncStatus.actionRequired;
    case OpStatus.pending:
    case OpStatus.failed:
      final dep = dependency?.state;
      if (dep == DependencyState.blocked || dep == DependencyState.orphaned) {
        return SyncStatus.actionRequired;
      }
      if (network.isOffline ||
          (network.reachability == Reachability.unknown && !op.everSent &&
              op.attempts == 0)) {
        return SyncStatus.savedOnDevice;
      }
      return SyncStatus.pendingSync;
  }
}

/// Counts per status for the dashboard (every status present, zero or not).
Map<SyncStatus, int> countByStatus(
  Outbox outbox,
  SyncPlanner planner, {
  required NetworkState network,
}) {
  final counts = {for (final s in SyncStatus.values) s: 0};
  for (final op in outbox.ops) {
    final s = statusOfOp(op,
        network: network, dependency: planner.infoFor(op));
    counts[s] = counts[s]! + 1;
  }
  return counts;
}

/// The one status shown in the app bar. Precedence: syncing > conflict >
/// action required > offline > pending > synced > online.
SyncStatus globalStatus({
  required Map<SyncStatus, int> counts,
  required NetworkState network,
  required bool running,
  required bool lastRunClean,
}) {
  if (running) return SyncStatus.syncing;
  if ((counts[SyncStatus.conflict] ?? 0) > 0) return SyncStatus.conflict;
  if ((counts[SyncStatus.actionRequired] ?? 0) > 0) {
    return SyncStatus.actionRequired;
  }
  if (network.isOffline) return SyncStatus.offline;
  final queued = (counts[SyncStatus.pendingSync] ?? 0) +
      (counts[SyncStatus.savedOnDevice] ?? 0) +
      (counts[SyncStatus.syncing] ?? 0);
  if (queued > 0) return SyncStatus.pendingSync;
  if (lastRunClean) return SyncStatus.synced;
  return SyncStatus.online;
}
