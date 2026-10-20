/// Sync-status widgets used on every screen: one vocabulary
/// ([SyncStatus]), one colour per status, and the online-only guard for
/// actions that must never be finalised offline.
///
/// Rebuild discipline (low-cost phones): each widget listens only to the
/// notifiers it needs ([AppGraph.revision], [AppGraph.lastSync],
/// [AppGraph.network]) through a single [ListenableBuilder], so a sync run
/// does not rebuild whole screens.
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../l10n/l10n.dart';
import '../sync/network.dart';
import '../sync/outbox.dart';
import '../sync/sync_status.dart';

String syncStatusLabel(AppLocalizations l, SyncStatus s) => switch (s) {
      SyncStatus.online => l.statusOnline,
      SyncStatus.offline => l.statusOffline,
      SyncStatus.savedOnDevice => l.statusSavedOnDevice,
      SyncStatus.pendingSync => l.statusPendingSync,
      SyncStatus.syncing => l.statusSyncing,
      SyncStatus.synced => l.statusSynced,
      SyncStatus.conflict => l.statusConflict,
      SyncStatus.actionRequired => l.statusActionRequired,
    };

Color syncStatusTone(SyncStatus s) => switch (s) {
      SyncStatus.online => const Color(0xFF1B7F5A),
      SyncStatus.synced => const Color(0xFF1B7F5A),
      SyncStatus.offline => const Color(0xFF5F6368),
      SyncStatus.savedOnDevice => const Color(0xFF0B5D8A),
      SyncStatus.pendingSync => const Color(0xFF0B5D8A),
      SyncStatus.syncing => const Color(0xFF6A4C93),
      SyncStatus.conflict => const Color(0xFFB3261E),
      SyncStatus.actionRequired => const Color(0xFF9A4F00),
    };

IconData syncStatusIcon(SyncStatus s) => switch (s) {
      SyncStatus.online => Icons.cloud_done_outlined,
      SyncStatus.offline => Icons.cloud_off_outlined,
      SyncStatus.savedOnDevice => Icons.phone_android_outlined,
      SyncStatus.pendingSync => Icons.schedule_outlined,
      SyncStatus.syncing => Icons.sync,
      SyncStatus.synced => Icons.check_circle_outline,
      SyncStatus.conflict => Icons.call_split,
      SyncStatus.actionRequired => Icons.error_outline,
    };

/// A status chip (text + icon, never colour alone — accessibility).
class SyncStatusChip extends StatelessWidget {
  const SyncStatusChip({super.key, required this.status, this.label});

  final SyncStatus status;

  /// Override text (e.g. "3 to sync"); defaults to the status name.
  final String? label;

  @override
  Widget build(BuildContext context) {
    final tone = syncStatusTone(status);
    final text = label ?? syncStatusLabel(context.l10n, status);
    return Semantics(
      label: text,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        decoration: BoxDecoration(
          color: tone.withValues(alpha: 0.12),
          border: Border.all(color: tone),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(syncStatusIcon(status), size: 14, color: tone),
            const SizedBox(width: 4),
            Flexible(
              child: Text(text,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: tone, fontSize: 12)),
            ),
          ],
        ),
      ),
    );
  }
}

/// Global status shown under the app bar; tap → Sync centre.
class GlobalSyncBar extends StatelessWidget {
  const GlobalSyncBar({super.key, required this.graph, this.onTap});

  final AppGraph graph;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge(
          [graph.revision, graph.lastSync, graph.network]),
      builder: (context, _) {
        final l = context.l10n;
        final counts = graph.statusCounts();
        final status = globalStatus(
          counts: counts,
          network: graph.network.value,
          running: graph.engine.isRunning,
          lastRunClean: graph.lastSync.value?.clean ?? false,
        );
        final queued = (counts[SyncStatus.pendingSync] ?? 0) +
            (counts[SyncStatus.savedOnDevice] ?? 0);
        final label = switch (status) {
          SyncStatus.pendingSync => l.globalToSync(queued),
          SyncStatus.conflict =>
            l.globalConflicts(counts[SyncStatus.conflict] ?? 0),
          SyncStatus.actionRequired =>
            l.globalNeedAction(counts[SyncStatus.actionRequired] ?? 0),
          SyncStatus.synced => l.globalAllSynced,
          SyncStatus.offline when queued > 0 =>
            l.globalOfflineSaved(queued),
          _ => syncStatusLabel(l, status),
        };
        return Material(
          color: syncStatusTone(status).withValues(alpha: 0.06),
          child: InkWell(
            key: const Key('global-sync-bar'),
            onTap: onTap,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              child: Row(
                children: [
                  SyncStatusChip(
                    key: Key('global-status-${status.name}'),
                    status: status,
                    label: label,
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

/// Text shown on every online-only finalisation control while offline.
String needsConnection(AppLocalizations l) => l.needsConnection;

/// A button for an action that is only ever finalised ONLINE and verified
/// by the server (sign Rx, confirm payment, complete consultation, post a
/// stock adjustment, print a signed document). Offline it is disabled and
/// says "Needs connection — will not be finalised offline". When the
/// network state is unknown the action is attempted; the server decides.
class OnlineOnlyButton extends StatelessWidget {
  const OnlineOnlyButton({
    super.key,
    required this.network,
    required this.label,
    required this.onPressed,
    this.icon,
    this.filled = false,
  });

  final NetworkMonitor network;
  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final bool filled;

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<NetworkState>(
      valueListenable: network,
      builder: (context, state, _) {
        final offline = state.isOffline;
        final action = offline ? null : onPressed;
        final child = Text(label);
        final button = filled
            ? (icon == null
                ? FilledButton(onPressed: action, child: child)
                : FilledButton.icon(
                    onPressed: action, icon: Icon(icon, size: 18), label: child))
            : (icon == null
                ? TextButton(onPressed: action, child: child)
                : TextButton.icon(
                    onPressed: action, icon: Icon(icon, size: 18), label: child));
        if (!offline) return button;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            button,
            Text(
              context.l10n.needsConnection,
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: Theme.of(context).colorScheme.error),
            ),
          ],
        );
      },
    );
  }
}

/// "Needs connection" panel for online-only screens (reports).
class NeedsConnectionPanel extends StatelessWidget {
  const NeedsConnectionPanel({super.key, this.onRetry});

  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return Card(
      key: const Key('needs-connection'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              const Icon(Icons.cloud_off_outlined),
              const SizedBox(width: 8),
              Expanded(child: Text(l.needsConnectionTitle)),
            ]),
            const SizedBox(height: 4),
            Text(l.needsConnectionReports,
                style: Theme.of(context).textTheme.bodySmall),
            if (onRetry != null)
              TextButton(onPressed: onRetry, child: Text(l.refresh)),
          ],
        ),
      ),
    );
  }
}

/// A sentence a receptionist can act on for an op's last failure.
String humanError(AppLocalizations l, OutboxOp op) {
  if (op.conflictReason == ConflictReason.maxAttempts) {
    return l.errMaxAttempts(op.attempts);
  }
  if (op.conflictReason == ConflictReason.wrongUser ||
      op.conflictReason == ConflictReason.orphaned) {
    return op.lastError;
  }
  final status = op.lastHttpStatus;
  if (op.lastError.isEmpty) return '';
  if (status == null) return l.errNetwork;
  if (status == 429) return l.errBusy;
  if (status >= 500 || status == 408) return l.errServer;
  if (status == 403) return l.errForbidden(op.lastError);
  if (status == 422) return l.errInvalid(op.lastError);
  return op.lastError;
}
