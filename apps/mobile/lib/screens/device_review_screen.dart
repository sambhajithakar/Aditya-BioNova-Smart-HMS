/// Clinician review of device readings on Android (M8.2): the same API and
/// rules as the web review panel. Online only — accepting writes the
/// encounter's vitals on the server, which is a finalising clinical action.
///
/// Accepting requires ticking "this reading belongs to `patient` and was
/// measured just now"; rejecting requires a reason. Readings are never
/// accepted automatically.
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../l10n/l10n.dart';
import 'device_capture_screen.dart' show ReadingSummary;
import 'devices_screen.dart' show SimulatedBadge;

class DeviceReviewScreen extends StatefulWidget {
  const DeviceReviewScreen({
    super.key,
    required this.graph,
    required this.encounterId,
    required this.patientLabel,
  });

  final AppGraph graph;
  final String encounterId;
  final String patientLabel;

  @override
  State<DeviceReviewScreen> createState() => _DeviceReviewScreenState();
}

class _DeviceReviewScreenState extends State<DeviceReviewScreen> {
  List<Map<String, dynamic>>? _pending;
  String? _notice;
  String? _error;
  bool _busy = false;

  AppGraph get graph => widget.graph;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final json = await graph.client.request('GET',
          '/device-readings?encounter_id=${widget.encounterId}&status=pending_review');
      if (!mounted) return;
      setState(() => _pending = [
            for (final r in (json as List? ?? const []))
              if (r is Map<String, dynamic>) r,
          ]);
    } catch (err) {
      if (mounted) setState(() => _error = context.l10n.reviewFailed('$err'));
    }
  }

  Future<void> _decide(Map<String, dynamic> r, bool accept) async {
    final l = context.l10n;
    Map<String, dynamic>? body;
    if (accept) {
      final ok = await _confirmAccept();
      if (ok != true) return;
      body = {'surface': 'android', 'confirm_patient': true};
    } else {
      final reason = await _askReason();
      if (reason == null) return;
      body = {'surface': 'android', 'reason': reason};
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await graph.client.requestMap(
          'POST', '/device-readings/${r['id']}/${accept ? 'accept' : 'reject'}',
          body: body);
      if (!mounted) return;
      setState(() => _notice = accept ? l.reviewAccepted : l.reviewRejected);
      await _load();
    } catch (err) {
      if (mounted) setState(() => _error = l.reviewFailed('$err'));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<bool?> _confirmAccept() {
    var ticked = false;
    return showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => AlertDialog(
          title: Text(ctx.l10n.reviewAccept),
          content: CheckboxListTile(
            key: const Key('review-confirm-patient'),
            value: ticked,
            onChanged: (v) => setLocal(() => ticked = v ?? false),
            title: Text(ctx.l10n.reviewConfirm(widget.patientLabel)),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: Text(ctx.l10n.cancel)),
            FilledButton(
              key: const Key('review-accept-ok'),
              onPressed: ticked ? () => Navigator.pop(ctx, true) : null,
              child: Text(ctx.l10n.reviewAccept),
            ),
          ],
        ),
      ),
    );
  }

  Future<String?> _askReason() {
    final ctl = TextEditingController();
    return showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(ctx.l10n.reviewReject),
        content: TextField(
          key: const Key('review-reason'),
          controller: ctl,
          decoration: InputDecoration(labelText: ctx.l10n.reviewReason),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: Text(ctx.l10n.cancel)),
          FilledButton(
            key: const Key('review-reject-ok'),
            onPressed: () {
              final v = ctl.text.trim();
              if (v.length >= 3) Navigator.pop(ctx, v);
            },
            child: Text(ctx.l10n.reviewReject),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final pending = _pending;
    return Scaffold(
      appBar: AppBar(title: Text(l.reviewTitle)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(l.measureFor(widget.patientLabel),
              key: const Key('review-patient'),
              style: Theme.of(context).textTheme.titleMedium),
          if (_busy) const LinearProgressIndicator(),
          if (_notice != null) Text(_notice!, key: const Key('review-notice')),
          if (_error != null)
            Text(_error!,
                key: const Key('review-error'),
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
          if (pending == null && _error == null)
            const Center(child: CircularProgressIndicator()),
          if (pending != null && pending.isEmpty)
            Text(l.reviewNone, key: const Key('review-none')),
          for (final r in pending ?? const <Map<String, dynamic>>[])
            Card(
              key: Key('review-${r['id']}'),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Flexible(child: Text('${r['device_label']}')),
                      if (r['device_is_simulator'] == true) ...[
                        const SizedBox(width: 6),
                        const SimulatedBadge(),
                      ],
                    ]),
                    ReadingSummary(
                      kind: '${r['kind']}',
                      values: (r['values'] as Map).cast<String, dynamic>(),
                      flags: [for (final f in (r['flags'] as List)) '$f'],
                      clockSkew: r['clock_skew'] == true,
                    ),
                    Wrap(spacing: 8, children: [
                      FilledButton(
                        key: Key('review-accept-${r['id']}'),
                        onPressed: _busy ? null : () => _decide(r, true),
                        child: Text(l.reviewAccept),
                      ),
                      OutlinedButton(
                        key: Key('review-reject-${r['id']}'),
                        onPressed: _busy ? null : () => _decide(r, false),
                        child: Text(l.reviewReject),
                      ),
                    ]),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
