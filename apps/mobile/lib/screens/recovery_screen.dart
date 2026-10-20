/// Shown when the encrypted offline store cannot be unlocked (audit H23):
/// a Keystore failure, a store restored from another device, or a damaged
/// file. The app does NOT continue in a memory-only mode — the user is
/// told what happened and chooses: try again, or reset the local data
/// after an explicit confirmation that unsynced items will be lost.
library;

import 'package:flutter/material.dart';

import '../boot.dart';

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
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Reset local data?'),
        content: const Text(
          'Everything stored on this device by the app is deleted: '
          'registrations, queue entries, invoices and prescription drafts '
          'that have not synced are LOST and cannot be recovered. '
          'Data already on the server is not affected. You will sign in '
          'again afterwards.',
        ),
        actions: [
          TextButton(
            key: const Key('recovery-reset-cancel'),
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const Key('recovery-reset-confirm'),
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(ctx).colorScheme.error,
            ),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Delete local data'),
          ),
        ],
      ),
    );
    if (confirmed == true) await _run(reset);
  }

  @override
  Widget build(BuildContext context) {
    final canReset = widget.failure.reset != null;
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            Icon(Icons.lock_reset,
                size: 48, color: Theme.of(context).colorScheme.error),
            const SizedBox(height: 12),
            Text(
              canReset
                  ? 'Offline data could not be unlocked'
                  : 'This build cannot start',
              key: const Key('recovery-title'),
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 12),
            if (canReset)
              const Text(
                'The work saved on this device is encrypted with a key kept '
                'in this phone\'s secure hardware. The key or the data could '
                'not be read — this happens after restoring the app onto a '
                'new phone, or if the stored file was damaged.\n\n'
                'The app will not continue without its offline storage, '
                'because new work would silently be lost. Try again first; '
                'if it keeps failing, reset the local data.',
              ),
            const SizedBox(height: 12),
            Text(
              'Details: ${widget.failure.error}',
              key: const Key('recovery-details'),
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 24),
            FilledButton(
              key: const Key('recovery-retry'),
              onPressed: _busy ? null : () => _run(widget.failure.retry),
              child: const Text('Try again'),
            ),
            if (canReset) ...[
              const SizedBox(height: 8),
              OutlinedButton(
                key: const Key('recovery-reset'),
                onPressed: _busy ? null : _confirmReset,
                style: OutlinedButton.styleFrom(
                  foregroundColor: Theme.of(context).colorScheme.error,
                ),
                child: const Text(
                  'Reset local data (unsynced items will be lost)',
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
