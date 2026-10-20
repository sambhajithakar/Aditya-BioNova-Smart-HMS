/// Small shared widgets: the explicit sync-state labels R4.2 asks for —
/// **Saved on device / Pending sync / Synced / Conflict** — plus the two
/// extra states the engine can be in (syncing, retryable failure) — and
/// the language picker / quick-pick chips shared by several screens.
library;

import 'package:flutter/material.dart';

import '../l10n/l10n.dart';
import '../settings/app_settings.dart';
import '../sync/outbox.dart';

/// Human label for an outbox op's state.
String opStateLabel(AppLocalizations l, OutboxOp op) => switch (op.status) {
      OpStatus.pending =>
        op.attempts == 0 ? l.opPending : l.opPendingRetry(op.attempts),
      OpStatus.inFlight => l.opSyncing,
      OpStatus.failed =>
        op.attempts > 1 ? l.opFailedAttempt(op.attempts) : l.opFailed,
      OpStatus.conflicted => l.stateConflict,
    };

class StateChip extends StatelessWidget {
  const StateChip({super.key, required this.label, required this.tone});

  final String label;
  final Color tone;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: tone.withValues(alpha: 0.15),
        border: Border.all(color: tone),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(color: tone, fontSize: 12),
      ),
    );
  }
}

/// Chip for an outbox op, coloured by its state.
class OpStateChip extends StatelessWidget {
  const OpStateChip({super.key, required this.op});

  final OutboxOp op;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final l = context.l10n;
    final state = opStateLabel(l, op);
    final (label, tone) = switch (op.status) {
      OpStatus.pending => (l.savedOnDevice(state), scheme.primary),
      OpStatus.inFlight => (state, scheme.tertiary),
      OpStatus.failed => (l.savedOnDevice(state), scheme.error),
      OpStatus.conflicted => (state, scheme.error),
    };
    return StateChip(label: label, tone: tone);
  }
}

/// Language picker (login + home): device language, English, मराठी,
/// हिंदी. The choice is stored on the device ([AppSettings]).
class LanguageMenuButton extends StatelessWidget {
  const LanguageMenuButton({super.key, required this.settings});

  final AppSettings settings;

  static const String _device = 'device';

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final current = settings.language ?? _device;
    return PopupMenuButton<String>(
      key: const Key('language-menu'),
      tooltip: l.languageMenu,
      icon: const Icon(Icons.translate),
      initialValue: current,
      onSelected: (code) =>
          settings.setLanguage(code == _device ? null : code),
      itemBuilder: (_) => [
        CheckedPopupMenuItem<String>(
          key: const Key('language-device'),
          value: _device,
          checked: current == _device,
          child: Text(l.languageDevice),
        ),
        for (final entry in kLanguageNames.entries)
          CheckedPopupMenuItem<String>(
            key: Key('language-${entry.key}'),
            value: entry.key,
            checked: current == entry.key,
            child: Text(entry.value),
          ),
      ],
    );
  }
}

/// A one-tap choice chip (Rural Clinic mode) with a guaranteed
/// [kRuralTouchTarget]-high touch target.
class QuickPickChip extends StatelessWidget {
  const QuickPickChip({
    super.key,
    required this.label,
    required this.selected,
    required this.onSelected,
    this.tooltip,
  });

  final String label;
  final bool selected;
  final VoidCallback onSelected;
  final String? tooltip;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: kRuralTouchTarget,
      child: ChoiceChip(
        label: Text(label),
        tooltip: tooltip,
        selected: selected,
        onSelected: (_) => onSelected(),
      ),
    );
  }
}
