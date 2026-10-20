/// Conflict resolution screens — the user decides, explicitly, every time.
///
/// Duplicate registration (409 with candidates):
/// * **Keep mine as a new patient** — re-send with `allow_duplicates`
///   under a new idempotency key (confirmed);
/// * **Use this server record** — my registration is NOT sent; the queued
///   visit / Rx / bill that referred to it are re-pointed to the existing
///   patient (the local ref maps to the server id), after a confirmation
///   naming how many changes move;
/// * **Merge by review** (online) — re-read the server record, tick the
///   fields to copy from my registration (nothing is pre-ticked), send ONLY
///   those with `PATCH /patients/{id}`, then continue as "use this record".
///
/// Version mismatch (409/412): show mine next to what the server said;
/// **Send mine again** (new key, confirmed) or **Use the server version**
/// (discard mine, with the dependants warning).
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../l10n/l10n.dart';
import '../sync/outbox.dart';
import 'sync_tab.dart' show confirmDialog, discardOp, registerAnyway;
import 'sync_widgets.dart';

/// Patient fields compared on the duplicate screen (API names).
const List<String> kPatientReviewFields = [
  'full_name',
  'gender',
  'date_of_birth',
  'phone',
  'address',
  'blood_group',
  'allergies',
];

String patientFieldLabel(AppLocalizations l, String f) => switch (f) {
      'full_name' => l.registerName,
      'gender' => l.registerGender,
      'date_of_birth' => l.fieldDob,
      'phone' => l.registerPhone,
      'address' => l.fieldAddress,
      'blood_group' => l.fieldBloodGroup,
      'allergies' => l.registerAllergies,
      _ => f,
    };

List<Map<String, dynamic>> duplicateCandidates(OutboxOp op) {
  final detail = op.serverSnapshot?['detail'];
  final raw = detail is Map ? detail['candidates'] : null;
  return (raw as List<dynamic>? ?? const [])
      .whereType<Map<dynamic, dynamic>>()
      .map((m) => m.cast<String, dynamic>())
      .toList();
}

class ConflictScreen extends StatefulWidget {
  const ConflictScreen({super.key, required this.graph, required this.op});

  final AppGraph graph;
  final OutboxOp op;

  @override
  State<ConflictScreen> createState() => _ConflictScreenState();
}

class _ConflictScreenState extends State<ConflictScreen> {
  AppGraph get graph => widget.graph;
  OutboxOp get op => widget.op;

  Future<void> _useServer(Map<String, dynamic> candidate) async {
    final l = context.l10n;
    final moved = graph.outbox.dependentsOf(op).length;
    final label = '${candidate['uhid'] ?? ''} ${candidate['full_name'] ?? ''}'
        .trim();
    final ok = await confirmDialog(
      context,
      title: l.useServerTitle(label),
      body: l.useServerBody(moved),
      action: l.useServerAction,
    );
    if (!ok || !mounted) return;
    await linkToServerPatient(graph, op, candidate);
    if (!mounted) return;
    Navigator.of(context).pop(context.l10n.useServerDone(label));
  }

  Future<void> _merge(Map<String, dynamic> candidate) async {
    final done = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(
        builder: (_) => MergeReviewScreen(
            graph: graph, op: op, candidateId: '${candidate['id']}'),
      ),
    );
    if (done != null && mounted) Navigator.of(context).pop(done);
  }

  Future<void> _keepMine() async {
    final name = await registerAnyway(context, graph, op);
    if (name == null || !mounted) return;
    Navigator.of(context).pop(context.l10n.registerAnywayNotice(name));
  }

  Future<void> _sendMine() async {
    final l = context.l10n;
    final ok = await confirmDialog(context,
        title: l.conflictSendMineTitle,
        body: l.conflictSendMineBody,
        action: l.conflictSendMine);
    if (!ok || !mounted) return;
    graph.outbox.reissue(op, Map<String, dynamic>.of(op.payload));
    Navigator.of(context).pop(l.conflictSentAgain);
  }

  Future<void> _discard() async {
    final msg = await discardOp(context, graph, op);
    if (msg != null && mounted) Navigator.of(context).pop(msg);
  }

  Widget _fieldTable(Map<String, dynamic> values, {Set<String>? differs}) {
    final l = context.l10n;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final f in kPatientReviewFields)
          if (values.containsKey(f))
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Text(
                '${patientFieldLabel(l, f)}: ${values[f] ?? '—'}',
                style: differs != null && differs.contains(f)
                    ? const TextStyle(fontWeight: FontWeight.bold)
                    : null,
              ),
            ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final duplicate = op.conflictReason == ConflictReason.duplicatePatient;
    final candidates = duplicate ? duplicateCandidates(op) : const [];
    return Scaffold(
      appBar: AppBar(title: Text(duplicate ? l.dupTitle : l.versionTitle)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(duplicate ? l.dupExplain : l.versionExplain),
          const SizedBox(height: 12),
          Text(l.conflictMine, style: Theme.of(context).textTheme.titleSmall),
          Card(
            key: const Key('conflict-mine'),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: duplicate
                  ? _fieldTable(op.payload)
                  : Text(_flat(op.payload)),
            ),
          ),
          const SizedBox(height: 12),
          Text(l.conflictServer, style: Theme.of(context).textTheme.titleSmall),
          if (duplicate)
            for (final c in candidates)
              Card(
                key: Key('candidate-${c['id']}'),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${c['uhid'] ?? ''}',
                          style: Theme.of(context).textTheme.labelLarge),
                      _fieldTable(c, differs: {
                        for (final f in kPatientReviewFields)
                          if (c.containsKey(f) &&
                              '${c[f] ?? ''}' != '${op.payload[f] ?? ''}')
                            f,
                      }),
                      if (c['matched_on'] is List)
                        Text(l.dupMatchedOn(
                            (c['matched_on'] as List).join(', '))),
                      Wrap(children: [
                        TextButton(
                          key: Key('use-server-${c['id']}'),
                          onPressed: () => _useServer(c),
                          child: Text(l.useServerAction),
                        ),
                        OnlineOnlyButton(
                          key: Key('merge-${c['id']}'),
                          network: graph.network,
                          label: l.mergeAction,
                          onPressed: () => _merge(c),
                        ),
                      ]),
                    ],
                  ),
                ),
              )
          else
            Card(
              key: const Key('conflict-server'),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Text(op.serverSnapshot == null
                    ? op.lastError
                    : _flat(op.serverSnapshot!)),
              ),
            ),
          const SizedBox(height: 16),
          Wrap(spacing: 8, runSpacing: 8, children: [
            if (duplicate)
              FilledButton(
                key: const Key('keep-mine-new'),
                onPressed: _keepMine,
                child: Text(l.keepMineNew),
              )
            else
              FilledButton(
                key: const Key('send-mine-again'),
                onPressed: _sendMine,
                child: Text(l.conflictSendMine),
              ),
            OutlinedButton(
              key: const Key('conflict-screen-discard'),
              onPressed: _discard,
              child: Text(duplicate ? l.conflictDiscard : l.useServerVersion),
            ),
          ]),
        ],
      ),
    );
  }

  static String _flat(Map<String, dynamic> m) => [
        for (final e in m.entries)
          if (e.value is! Map && e.value is! List) '${e.key}: ${e.value}'
          else '${e.key}: …',
      ].join('\n');
}

/// Point a queued registration's local ref at an EXISTING server patient:
/// the registration is dropped (never sent); dependants push against it.
Future<void> linkToServerPatient(
    AppGraph graph, OutboxOp op, Map<String, dynamic> candidate) async {
  final ref = op.localRef;
  final serverId = '${candidate['id']}';
  if (ref != null) {
    graph.idMap.put(ref, serverId);
    await graph.store.saveSection('idmap', graph.idMap.toJson());
    await graph.directory.removeLocalPatient(ref);
  }
  await graph.directory.rememberFetched([
    {
      'id': serverId,
      'uhid': candidate['uhid'] ?? '',
      'full_name': candidate['full_name'] ?? '',
      'gender': candidate['gender'] ?? 'unknown',
      'phone': candidate['phone'] ?? '',
    },
  ]);
  graph.outbox.resolveUsingServer(op);
  await graph.adoptSynced();
}

/// Merge by review: the server record is re-read ONLINE, nothing is
/// pre-selected, only ticked fields are sent.
class MergeReviewScreen extends StatefulWidget {
  const MergeReviewScreen({
    super.key,
    required this.graph,
    required this.op,
    required this.candidateId,
  });

  final AppGraph graph;
  final OutboxOp op;
  final String candidateId;

  @override
  State<MergeReviewScreen> createState() => _MergeReviewScreenState();
}

class _MergeReviewScreenState extends State<MergeReviewScreen> {
  Map<String, dynamic>? _server;
  String? _error;
  final Set<String> _take = <String>{};
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final p = await widget.graph.client.getPatient(widget.candidateId);
      if (mounted) setState(() => _server = p);
    } catch (err) {
      if (mounted) setState(() => _error = err.toString());
    }
  }

  List<String> get _differing {
    final s = _server;
    if (s == null) return const [];
    return [
      for (final f in kPatientReviewFields)
        if (widget.op.payload.containsKey(f) &&
            '${widget.op.payload[f] ?? ''}'.isNotEmpty &&
            '${widget.op.payload[f] ?? ''}' != '${s[f] ?? ''}')
          f,
    ];
  }

  Future<void> _apply() async {
    final server = _server;
    if (server == null) return;
    final s = <String, dynamic>{...server};
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (_take.isNotEmpty) {
        final fields = {for (final f in _take) f: widget.op.payload[f]};
        final updated =
            await widget.graph.client.patchPatient(widget.candidateId, fields);
        s.addAll(updated);
      }
      await linkToServerPatient(widget.graph, widget.op, s);
      if (!mounted) return;
      Navigator.of(context)
          .pop(context.l10n.mergeDone(_take.length, '${s['uhid'] ?? ''}'));
    } catch (err) {
      if (mounted) setState(() => _error = err.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final s = _server;
    return Scaffold(
      appBar: AppBar(title: Text(l.mergeTitle)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(l.mergeExplain),
          const SizedBox(height: 12),
          if (_error != null)
            Text(_error!,
                key: const Key('merge-error'),
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
          if (s == null && _error == null) const LinearProgressIndicator(),
          if (s != null && _differing.isEmpty) Text(l.mergeNothing),
          for (final f in _differing)
            CheckboxListTile(
              key: Key('merge-field-$f'),
              value: _take.contains(f),
              onChanged: (v) => setState(
                  () => v == true ? _take.add(f) : _take.remove(f)),
              title: Text(patientFieldLabel(l, f)),
              subtitle: Text(l.mergeFieldLine(
                  '${s![f] ?? '—'}', '${widget.op.payload[f] ?? '—'}')),
            ),
          const SizedBox(height: 12),
          OnlineOnlyButton(
            key: const Key('merge-apply'),
            network: widget.graph.network,
            filled: true,
            label: l.mergeApply(_take.length),
            onPressed: s == null || _busy ? null : _apply,
          ),
        ],
      ),
    );
  }
}
