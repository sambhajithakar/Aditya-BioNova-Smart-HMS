/// Appointments tab (reception): appointment DRAFTS that work offline,
/// plus today's server list when online.
///
/// A draft queues `POST /appointments`; the server still checks the slot
/// (an overlapping booking is a 409 → **Conflict**, resolved by a person).
/// A patient registered offline can be booked straight away: the draft
/// refers to `$ref:<local>` and waits for the registration to sync.
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../data/directory.dart';
import '../l10n/l10n.dart';
import '../sync/outbox.dart';
import '../sync/planner.dart';
import '../sync/sync_status.dart';
import 'sync_widgets.dart';

/// Appointment start times offered as quick picks.
const List<String> kSlotTimes = ['09:00', '10:00', '11:00', '12:00', '15:00', '16:00', '17:00'];

class AppointmentsTab extends StatefulWidget {
  const AppointmentsTab({super.key, required this.graph});

  final AppGraph graph;

  @override
  State<AppointmentsTab> createState() => _AppointmentsTabState();
}

class _AppointmentsTabState extends State<AppointmentsTab> {
  String? _patientId;
  DateTime _day = DateTime.now();
  String _time = kSlotTimes.first;
  final _reason = TextEditingController();
  String? _notice;
  String? _error;
  List<Map<String, dynamic>>? _today;

  AppGraph get graph => widget.graph;

  @override
  void initState() {
    super.initState();
    _patientId = graph.directory.resolveSelection(null, graph.idMap);
    graph.revision.addListener(_changed);
    _loadToday();
  }

  @override
  void dispose() {
    graph.revision.removeListener(_changed);
    _reason.dispose();
    super.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  static String _date(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';

  Future<void> _loadToday() async {
    try {
      final today = _date(DateTime.now());
      final page = await graph.client.listAppointments(today, today);
      if (mounted) {
        setState(() => _today = DirectoryCache.listOf(page['items']));
      }
    } catch (_) {
      if (mounted) setState(() => _today = null);
    }
  }

  Future<void> _save() async {
    final l = context.l10n;
    final patientId =
        graph.directory.resolveSelection(_patientId, graph.idMap);
    final branches = graph.directory.branches;
    if (patientId == null) {
      setState(() => _error = l.pickPatientFirst);
      return;
    }
    if (branches.isEmpty) {
      setState(() => _error = l.consultNoBranch);
      return;
    }
    final parts = _time.split(':');
    final start = DateTime(_day.year, _day.month, _day.day,
        int.parse(parts[0]), int.parse(parts[1]));
    final end = start.add(const Duration(minutes: 15));
    final localRef = Outbox.newId();
    final op = graph.outbox.enqueue(
      entity: 'appointment',
      method: 'POST',
      path: '/appointments',
      payload: {
        'patient_id': graph.directory.refFor(patientId, graph.idMap),
        'branch_id': branches.first['id'],
        'starts_at': start.toUtc().toIso8601String(),
        'ends_at': end.toUtc().toIso8601String(),
        'reason': _reason.text.trim(),
      },
      dedupeKey: 'appointment:$patientId:${start.toIso8601String()}',
      localRef: localRef,
    );
    if (op.localRef != localRef) {
      setState(() {
        _error = null;
        _notice = l.appointmentDuplicate;
      });
      return;
    }
    await graph.appointments.add(localRef, {
      'patientLabel': graph.directory.patientLabel(patientId),
      'when': '${_date(_day)} $_time',
      'reason': _reason.text.trim(),
    });
    graph.scheduler.requestSync();
    if (!mounted) return;
    setState(() {
      _error = null;
      _notice = context.l10n.appointmentSaved;
      _reason.clear();
    });
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final dir = graph.directory;
    final planner = SyncPlanner(graph.outbox.ops, graph.idMap);
    final today = _today;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(l.appointmentsTitle,
            style: Theme.of(context).textTheme.titleMedium),
        DropdownButton<String>(
          key: const Key('appt-patient'),
          isExpanded: true,
          value: dir.resolveSelection(_patientId, graph.idMap),
          hint: const Text('—'),
          items: [
            for (final p in dir.patients)
              DropdownMenuItem<String>(
                value: p['id'] as String,
                child: Text(dir.pickerLabel(p, graph.idMap,
                    pendingTag: l.pendingSyncTag, syncedTag: l.syncedTag)),
              ),
          ],
          onChanged: (v) => setState(() => _patientId = v),
        ),
        ListTile(
          key: const Key('appt-day'),
          contentPadding: EdgeInsets.zero,
          title: Text(l.appointmentDay(_date(_day))),
          trailing: TextButton(
            onPressed: () async {
              final now = DateTime.now();
              final picked = await showDatePicker(
                context: context,
                initialDate: _day,
                firstDate: DateTime(now.year, now.month, now.day),
                lastDate: now.add(const Duration(days: 180)),
              );
              if (picked != null && mounted) setState(() => _day = picked);
            },
            child: Text(l.pick),
          ),
        ),
        Wrap(
          spacing: 6,
          runSpacing: 4,
          children: [
            for (final t in kSlotTimes)
              ChoiceChip(
                key: Key('appt-time-$t'),
                label: Text(t),
                selected: _time == t,
                onSelected: (_) => setState(() => _time = t),
              ),
          ],
        ),
        TextField(
          key: const Key('appt-reason'),
          controller: _reason,
          decoration: InputDecoration(labelText: l.appointmentReason),
        ),
        const SizedBox(height: 12),
        FilledButton(
          key: const Key('appt-save'),
          onPressed: _save,
          child: Text(l.appointmentSave),
        ),
        if (_notice != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_notice!, key: const Key('appt-notice')),
          ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_error!,
                key: const Key('appt-error'),
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
        const SizedBox(height: 16),
        Text(l.appointmentDrafts,
            style: Theme.of(context).textTheme.titleSmall),
        for (final d in graph.appointments.drafts)
          ListTile(
            key: Key('appt-draft-${d['localRef']}'),
            contentPadding: EdgeInsets.zero,
            title: Text('${d['patientLabel'] ?? ''} · ${d['when'] ?? ''}'),
            subtitle: Align(
              alignment: Alignment.centerLeft,
              child: () {
                final op = graph.outbox.creatorOf('${d['localRef']}');
                if (d['discarded'] == true) return Text(l.stateDiscarded);
                return SyncStatusChip(
                  status: op == null
                      ? SyncStatus.synced
                      : statusOfOp(op,
                          network: graph.network.value,
                          dependency: planner.infoFor(op)),
                );
              }(),
            ),
          ),
        const SizedBox(height: 16),
        Row(children: [
          Expanded(
            child: Text(l.appointmentsToday,
                style: Theme.of(context).textTheme.titleSmall),
          ),
          TextButton(onPressed: _loadToday, child: Text(l.refresh)),
        ]),
        if (today == null)
          NeedsConnectionPanel(onRetry: _loadToday)
        else if (today.isEmpty)
          Text(l.appointmentsNone)
        else
          for (final a in today)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              title: Text(
                  '${'${a['starts_at'] ?? ''}'.replaceFirst('T', ' ').split('.').first} · '
                  '${dir.patientLabel('${a['patient_id']}')}'),
              subtitle: Text('${a['status'] ?? ''} ${a['reason'] ?? ''}'),
            ),
      ],
    );
  }
}
