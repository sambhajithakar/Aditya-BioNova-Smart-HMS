/// Registration tab: register a walk-in with no network.
///
/// The record is queued in the outbox with a device id; the same-day
/// `patient:<name>:<phone>` dedupe key collapses a double-tap into ONE op,
/// and the new patient appears in the cached directory immediately (as
/// "pending sync"), so reception can put them into today's queue right
/// away. Any later op that needs their id is pushed after the registration
/// — the sync engine substitutes the server id automatically.
///
/// The server's own duplicate check still applies at sync time: a 409
/// parks the op as a **Conflict** for a human to resolve (never a silent
/// last-write-wins).
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../l10n/l10n.dart';
import '../settings/app_settings.dart';
import '../sync/outbox.dart';
import '../util/dates.dart';

const List<String> _genders = ['female', 'male', 'other', 'unknown'];

class RegisterTab extends StatefulWidget {
  const RegisterTab({super.key, required this.graph});

  final AppGraph graph;

  @override
  State<RegisterTab> createState() => _RegisterTabState();
}

class _RegisterTabState extends State<RegisterTab> {
  final _name = TextEditingController();
  final _phone = TextEditingController();
  final _allergies = TextEditingController();
  String _gender = 'female';
  DateTime? _dob;
  String? _error;
  String? _notice;

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    _allergies.dispose();
    super.dispose();
  }

  bool get _hasDuplicateCandidate {
    final name = _name.text.trim().toLowerCase();
    final phone = _phone.text.trim();
    for (final p in widget.graph.directory.patients) {
      final sameName = ((p['full_name'] as String?) ?? '').trim().toLowerCase() == name;
      final samePhone =
          phone.isNotEmpty && ((p['phone'] as String?) ?? '').trim() == phone;
      if (sameName && (samePhone || phone.isEmpty)) return true;
    }
    return false;
  }

  Future<void> _register() async {
    final name = _name.text.trim();
    if (name.length < 2) {
      setState(() => _error = context.l10n.registerNameRequired);
      return;
    }
    final phone = _phone.text.trim();
    if (_hasDuplicateCandidate) {
      setState(() {
        _error = null;
        _notice = context.l10n.registerLooksDuplicate;
      });
      return;
    }

    final localRef = Outbox.newId();
    final today = localDay();
    final op = widget.graph.outbox.enqueue(
      entity: 'patient',
      method: 'POST',
      path: '/patients',
      payload: {
        'full_name': name,
        'gender': _gender,
        'date_of_birth':
            _dob?.toUtc().toIso8601String(),
        'dob_estimated': _dob == null,
        'phone': phone,
        'allergies': _allergies.text.trim(),
      },
      dedupeKey: 'patient:$name:${phone.toLowerCase()}:$today',
      localRef: localRef,
    );

    if (op.localRef != localRef) {
      setState(() {
        _error = null;
        _notice = context.l10n.registerDuplicateQueued;
      });
      return;
    }

    await widget.graph.directory.addLocalPatient(
      localRef: localRef,
      fullName: name,
      gender: _gender,
      phone: phone,
    );
    widget.graph.scheduler.requestSync();
    if (!mounted) return;
    setState(() {
      _error = null;
      _notice = context.l10n.registerSaved;
    });
    _name.clear();
    _phone.clear();
    _allergies.clear();
    _dob = null;
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final rural = widget.graph.settings.ruralMode;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(l.registerTitle,
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 12),
        TextField(
          key: const Key('register-name'),
          controller: _name,
          decoration: InputDecoration(labelText: l.registerName),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          key: const Key('register-gender'),
          initialValue: _gender,
          decoration: InputDecoration(labelText: l.registerGender),
          itemHeight: rural ? kRuralTouchTarget + 8 : null,
          items: [
            for (final g in _genders)
              DropdownMenuItem(value: g, child: Text(genderLabel(l, g))),
          ],
          onChanged: (v) => setState(() => _gender = v ?? 'unknown'),
        ),
        const SizedBox(height: 12),
        TextField(
          key: const Key('register-phone'),
          controller: _phone,
          keyboardType: TextInputType.phone,
          decoration: InputDecoration(labelText: l.registerPhone),
        ),
        const SizedBox(height: 12),
        ListTile(
          key: const Key('register-dob'),
          contentPadding: EdgeInsets.zero,
          title: Text(_dob == null
              ? l.registerDobUnknown
              : l.registerDob(
                  _dob!.toLocal().toString().split(' ').first)),
          trailing: TextButton(
            onPressed: () async {
              final now = DateTime.now();
              final picked = await showDatePicker(
                context: context,
                initialDate: DateTime(now.year - 30, now.month, now.day),
                firstDate: DateTime(now.year - 120),
                lastDate: now,
              );
              if (picked != null && mounted) setState(() => _dob = picked);
            },
            child: Text(l.pick),
          ),
        ),
        TextField(
          key: const Key('register-allergies'),
          controller: _allergies,
          decoration: InputDecoration(labelText: l.registerAllergies),
        ),
        const SizedBox(height: 16),
        FilledButton(
          key: const Key('register-add'),
          onPressed: _register,
          child: Text(l.registerAdd),
        ),
        if (_notice != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_notice!, key: const Key('register-notice')),
          ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              _error!,
              key: const Key('register-error'),
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        const SizedBox(height: 16),
        Text(
          l.outboxCountsShort(
            widget.graph.outbox.count(OpStatus.pending),
            widget.graph.outbox.count(OpStatus.conflicted),
          ),
          key: const Key('register-outbox-counts'),
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ],
    );
  }
}
