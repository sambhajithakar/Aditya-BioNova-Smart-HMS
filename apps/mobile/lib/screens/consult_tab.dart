/// Consult tab (doctor): consultation-note DRAFTS that work offline.
///
/// "Save note draft" queues `POST /encounters` (chief complaint, history,
/// examination) with a local ref; until the draft has been sent it can be
/// edited in place (the queued op's body is replaced — never after it was
/// sent, see `OutboxOp.editable`). **Completing** the consultation is an
/// online, server-verified action (`POST /encounters/{id}/complete`) and is
/// only possible once the server has the encounter: offline the button
/// says "Needs connection — will not be finalised offline".
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../l10n/l10n.dart';
import '../sync/outbox.dart';
import '../sync/planner.dart';
import '../sync/sync_status.dart';
import '../util/dates.dart';
import 'sync_widgets.dart';

class ConsultTab extends StatefulWidget {
  const ConsultTab({super.key, required this.graph});

  final AppGraph graph;

  @override
  State<ConsultTab> createState() => _ConsultTabState();
}

class _ConsultTabState extends State<ConsultTab> {
  String? _patientId;
  String? _editing; // localRef of the draft being edited
  final _complaint = TextEditingController();
  final _history = TextEditingController();
  final _exam = TextEditingController();
  String? _notice;
  String? _error;

  AppGraph get graph => widget.graph;

  @override
  void initState() {
    super.initState();
    _patientId = graph.directory.resolveSelection(null, graph.idMap);
    graph.revision.addListener(_changed);
  }

  @override
  void dispose() {
    graph.revision.removeListener(_changed);
    _complaint.dispose();
    _history.dispose();
    _exam.dispose();
    super.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  Map<String, dynamic> _payload(String patientId) {
    final branches = graph.directory.branches;
    return {
      'patient_id': graph.directory.refFor(patientId, graph.idMap),
      'branch_id': branches.isNotEmpty ? branches.first['id'] : null,
      'chief_complaint': _complaint.text.trim(),
      'history': _history.text.trim(),
      'examination': _exam.text.trim(),
    };
  }

  Future<void> _save() async {
    final l = context.l10n;
    final patientId =
        graph.directory.resolveSelection(_patientId, graph.idMap);
    if (patientId == null) {
      setState(() => _error = l.pickPatientFirst);
      return;
    }
    if (_complaint.text.trim().isEmpty) {
      setState(() => _error = l.consultComplaintRequired);
      return;
    }
    if (graph.directory.branches.isEmpty) {
      setState(() => _error = l.consultNoBranch);
      return;
    }
    final editing = _editing;
    if (editing != null) {
      final op = graph.outbox.creatorOf(editing);
      if (op == null || !op.editable) {
        setState(() => _error = l.consultAlreadySent);
        return;
      }
      op.replacePayload(_payload(patientId));
      graph.outbox.markDirty();
      await graph.consults.update(editing, {
        'complaint': _complaint.text.trim(),
        'history': _history.text.trim(),
        'exam': _exam.text.trim(),
      });
    } else {
      final localRef = Outbox.newId();
      final op = graph.outbox.enqueue(
        entity: 'encounter',
        method: 'POST',
        path: '/encounters',
        payload: _payload(patientId),
        dedupeKey: 'encounter:$patientId:${localDay()}',
        localRef: localRef,
      );
      if (op.localRef != localRef) {
        setState(() {
          _error = null;
          _notice = l.consultDuplicate;
        });
        return;
      }
      await graph.consults.add(localRef, {
        'patientLabel': graph.directory.patientLabel(patientId),
        'complaint': _complaint.text.trim(),
        'history': _history.text.trim(),
        'exam': _exam.text.trim(),
      });
      graph.scheduler.requestSync();
    }
    if (!mounted) return;
    setState(() {
      _error = null;
      _editing = null;
      _notice = context.l10n.consultSaved;
      _complaint.clear();
      _history.clear();
      _exam.clear();
    });
  }

  void _edit(Map<String, dynamic> d) {
    setState(() {
      _editing = d['localRef'] as String?;
      _complaint.text = '${d['complaint'] ?? ''}';
      _history.text = '${d['history'] ?? ''}';
      _exam.text = '${d['exam'] ?? ''}';
      _notice = null;
    });
  }

  Future<void> _complete(Map<String, dynamic> d) async {
    final id = d['serverId'] as String?;
    if (id == null) return;
    try {
      await graph.client.completeEncounter(id);
      await graph.consults.setFlag('${d['localRef']}', 'completed');
      if (mounted) setState(() => _notice = context.l10n.consultCompleted);
    } catch (err) {
      if (mounted) setState(() => _error = err.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final dir = graph.directory;
    final planner = SyncPlanner(graph.outbox.ops, graph.idMap);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(l.consultTitle, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        DropdownButton<String>(
          key: const Key('consult-patient'),
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
        TextField(
          key: const Key('consult-complaint'),
          controller: _complaint,
          decoration: InputDecoration(labelText: l.consultComplaint),
        ),
        TextField(
          key: const Key('consult-history'),
          controller: _history,
          maxLines: 3,
          minLines: 1,
          decoration: InputDecoration(labelText: l.consultHistory),
        ),
        TextField(
          key: const Key('consult-exam'),
          controller: _exam,
          maxLines: 3,
          minLines: 1,
          decoration: InputDecoration(labelText: l.consultExam),
        ),
        const SizedBox(height: 12),
        FilledButton(
          key: const Key('consult-save'),
          onPressed: _save,
          child: Text(_editing == null ? l.consultSave : l.consultUpdate),
        ),
        if (_notice != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_notice!, key: const Key('consult-notice')),
          ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_error!,
                key: const Key('consult-error'),
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
        const SizedBox(height: 16),
        Text(l.consultDrafts, style: Theme.of(context).textTheme.titleSmall),
        for (final d in graph.consults.drafts)
          _draftCard(d, planner),
        if (graph.consults.drafts.isEmpty)
          Text(l.consultNoDrafts, style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }

  Widget _draftCard(Map<String, dynamic> d, SyncPlanner planner) {
    final l = context.l10n;
    final ref = '${d['localRef']}';
    final op = graph.outbox.creatorOf(ref);
    final serverId = d['serverId'] as String?;
    final completed = d['completed'] == true;
    final SyncStatus status = op != null
        ? statusOfOp(op,
            network: graph.network.value, dependency: planner.infoFor(op))
        : SyncStatus.synced;
    return Card(
      key: Key('consult-draft-$ref'),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${d['patientLabel'] ?? ''} — ${d['complaint'] ?? ''}',
                style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 4),
            if (d['discarded'] == true)
              Text(l.stateDiscarded)
            else
              SyncStatusChip(status: status),
            Wrap(children: [
              if (op != null && op.editable)
                TextButton(
                  key: Key('consult-edit-$ref'),
                  onPressed: () => _edit(d),
                  child: Text(l.consultEdit),
                ),
              if (completed)
                Padding(
                  padding: const EdgeInsets.all(8),
                  child: Text(l.consultCompleted),
                )
              else if (d['discarded'] != true)
                OnlineOnlyButton(
                  key: Key('consult-complete-$ref'),
                  network: graph.network,
                  label: serverId == null
                      ? l.consultCompleteAfterSync
                      : l.consultComplete,
                  onPressed: serverId == null ? null : () => _complete(d),
                ),
            ]),
          ],
        ),
      ),
    );
  }
}
