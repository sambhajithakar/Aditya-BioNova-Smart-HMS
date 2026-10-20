/// Shown when the encrypted offline store cannot be unlocked (audit H23):
/// a Keystore failure, a store restored from another device, or a damaged
/// file. The app does NOT continue in a memory-only mode — the user is
/// told what happened and chooses: try again, or reset the local data
/// after an explicit confirmation that unsynced items will be lost.
library;

import 'package:flutter/material.dart';

import '../boot.dart';
import '../l10n/l10n.dart';

class StoreRecoveryScreen extends StatefulWidget {
  const StoreRecoveryScreen({
    super.key,
    required this.failure,
    required this.onOutcome,
  });

  final BootFailed failure;

  /// Receives the result of "Try again" / "Reset".
  final void Function(BootOutcome outcome) onOutcome;

  @override
  State<StoreRecoveryScreen> createState() => _StoreRecoveryScreenState();
}

class _StoreRecoveryScreenState extends State<StoreRecoveryScreen> {
  bool _busy = false;

  Future<void> _run(Future<BootOutcome> Function() action) async {
    setState(() => _busy = true);
    final outcome = await action();
    if (!mounted) return;
    setState(() => _busy = false);
    widget.onOutcome(outcome);
  }

  Future<void> _confirmReset() async {
    final reset = widget.failure.reset;
    if (reset == null) return;
    final l = context.l10n;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l.recoveryResetTitle),
        content: Text(l.recoveryResetBody),
        actions: [
          TextButton(
            key: const Key('recovery-reset-cancel'),
            onPressed: () => Navigator.of(ctx).pop(false),
            child: Text(l.cancel),
          ),
          FilledButton(
            key: const Key('recovery-reset-confirm'),
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(ctx).colorScheme.error,
            ),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(l.recoveryResetConfirm),
          ),
        ],
      ),
    );
    if (confirmed == true) await _run(reset);
  }

  @override
  Widget build(BuildContext context) {
    final canReset = widget.failure.reset != null;
    final l = context.l10n;
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            Icon(Icons.lock_reset,
                size: 48, color: Theme.of(context).colorScheme.error),
            const SizedBox(height: 12),
            Text(
              canReset ? l.recoveryTitle : l.recoveryTitleFatal,
              key: const Key('recovery-title'),
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 12),
            if (canReset) Text(l.recoveryBody),
            const SizedBox(height: 12),
            Text(
              l.recoveryDetails('${widget.failure.error}'),
              key: const Key('recovery-details'),
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 24),
            FilledButton(
              key: const Key('recovery-retry'),
              onPressed: _busy ? null : () => _run(widget.failure.retry),
              child: Text(l.recoveryRetry),
            ),
            if (canReset) ...[
              const SizedBox(height: 8),
              OutlinedButton(
                key: const Key('recovery-reset'),
                onPressed: _busy ? null : _confirmReset,
                style: OutlinedButton.styleFrom(
                  foregroundColor: Theme.of(context).colorScheme.error,
                ),
                child: Text(l.recoveryReset),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
