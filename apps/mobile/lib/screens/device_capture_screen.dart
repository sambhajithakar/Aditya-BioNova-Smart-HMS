/// Measure with a device for ONE consultation (M8.2).
///
/// Patient context comes first: the screen is opened from a consultation
/// draft, and its patient is shown at the top for the whole flow. The
/// measurement is parsed on the phone only to show what the device sent;
/// "Save for clinician review" queues the RAW payload in the encrypted
/// outbox. Nothing here writes to the record: the API parses the bytes
/// again and a clinician must accept the reading (web or Android).
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../devices/device_book.dart';
import '../devices/simulator.dart';
import '../devices/transport.dart';
import '../l10n/l10n.dart';
import 'devices_screen.dart' show SimulatedBadge, deviceKindLabel;

const String kAppVersion = '1.0.0+m8.2';

/// Values, flags and clock note for a parsed reading (shared with review).
class ReadingSummary extends StatelessWidget {
  const ReadingSummary({
    super.key,
    required this.kind,
    required this.values,
    required this.flags,
    this.clockSkew = false,
  });

  final String kind;
  final Map<String, dynamic> values;
  final List<String> flags;
  final bool clockSkew;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final lines = <String>[
      if (kind == 'blood_pressure')
        l.readingBp('${values['systolic']}', '${values['diastolic']}')
      else
        l.readingSpo2('${values['spo2']}'),
      if (values['pulse'] != null) l.readingPulse('${values['pulse']}'),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final line in lines)
          Text(line, style: Theme.of(context).textTheme.titleLarge),
        // device-reported conditions are shown, never hidden
        if (flags.isNotEmpty)
          Text(l.measureFlags(flags.join(', ')),
              key: const Key('reading-flags')),
        if (clockSkew) Text(l.readingClockSkew, key: const Key('reading-clock')),
      ],
    );
  }
}

class DeviceCaptureScreen extends StatefulWidget {
  const DeviceCaptureScreen({
    super.key,
    required this.graph,
    required this.encounterRef,
    required this.patientLabel,
  });

  final AppGraph graph;

  /// Server encounter id, or the `$ref:` placeholder of a draft not yet synced.
  final String encounterRef;
  final String patientLabel;

  @override
  State<DeviceCaptureScreen> createState() => _DeviceCaptureScreenState();
}

class _DeviceCaptureScreenState extends State<DeviceCaptureScreen> {
  String _kind = DeviceKinds.bp;
  String? _deviceId;
  String? _scenario;
  bool _measuring = false;
  CaptureResult? _result;
  String? _error;
  String? _notice;

  AppGraph get graph => widget.graph;

  List<Map<String, dynamic>> get _paired => [
        for (final d in graph.devices.active(kind: _kind))
          if (graph.devices.isPaired('${d['id']}')) d,
      ];

  Map<String, dynamic>? get _device {
    for (final d in _paired) {
      if (d['id'] == _deviceId) return d;
    }
    return _paired.isEmpty ? null : _paired.first;
  }

  Future<void> _measure() async {
    final device = _device;
    if (device == null) return;
    final address = graph.devices.addressOf('${device['id']}')!;
    setState(() {
      _measuring = true;
      _result = null;
      _error = null;
      _notice = null;
    });
    try {
      final m = await graph.deviceTransport.measure(address,
          kind: _kind,
          scenario: device['is_simulator'] == true ? _scenario : null);
      final r = parseMeasurement(m);
      if (mounted) setState(() => _result = r);
    } catch (err) {
      if (mounted) setState(() => _error = context.l10n.measureError('$err'));
    } finally {
      if (mounted) setState(() => _measuring = false);
    }
  }

  void _save() {
    final r = _result;
    final device = _device;
    if (r == null || r.refusal != null || device == null) return;
    queueReading(
      graph.outbox,
      result: r,
      device: device,
      address: graph.devices.addressOf('${device['id']}')!,
      encounterRef: widget.encounterRef,
      appVersion: kAppVersion,
    );
    graph.scheduler.requestSync();
    setState(() {
      _result = null;
      _notice = context.l10n.measureSaved;
    });
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final device = _device;
    final r = _result;
    final simulated = device?['is_simulator'] == true;
    return Scaffold(
      appBar: AppBar(title: Text(l.measureWithDevice)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            color: Theme.of(context).colorScheme.primaryContainer,
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Text(l.measureFor(widget.patientLabel),
                  key: const Key('measure-patient'),
                  style: Theme.of(context).textTheme.titleMedium),
            ),
          ),
          SegmentedButton<String>(
            key: const Key('measure-kind'),
            segments: [
              ButtonSegment(value: DeviceKinds.bp, label: Text(l.deviceKindBp)),
              ButtonSegment(
                  value: DeviceKinds.oximeter, label: Text(l.deviceKindOximeter)),
            ],
            selected: {_kind},
            onSelectionChanged: (s) => setState(() {
              _kind = s.first;
              _deviceId = null;
              _scenario = null;
              _result = null;
            }),
          ),
          const SizedBox(height: 8),
          if (_paired.isEmpty)
            Text(l.measureNoPairedDevice, key: const Key('measure-no-device'))
          else
            DropdownButton<String>(
              key: const Key('measure-device'),
              isExpanded: true,
              value: '${device!['id']}',
              items: [
                for (final d in _paired)
                  DropdownMenuItem(
                      value: '${d['id']}',
                      child: Text('${d['label']} · '
                          '${deviceKindLabel(context, d['kind'] as String?)}')),
              ],
              onChanged: (v) => setState(() {
                _deviceId = v;
                _result = null;
              }),
            ),
          if (simulated && kDeviceSimulator) ...[
            Row(children: [const SimulatedBadge(), const SizedBox(width: 8),
              Text(l.measureScenario)]),
            DropdownButton<String>(
              key: const Key('measure-scenario'),
              isExpanded: true,
              value: _scenario ??
                  simScenarios.firstWhere((s) => s.kind == _kind).key,
              items: [
                for (final s in simScenarios)
                  if (s.kind == _kind)
                    DropdownMenuItem(value: s.key, child: Text(s.label)),
              ],
              onChanged: (v) => setState(() => _scenario = v),
            ),
          ],
          const SizedBox(height: 8),
          FilledButton(
            key: const Key('measure-start'),
            onPressed: device == null || _measuring ? null : _measure,
            child: Text(l.measureStart),
          ),
          if (_measuring) ...[
            const SizedBox(height: 8),
            const LinearProgressIndicator(),
            Text(l.measureWaiting),
          ],
          if (r != null) ...[
            const SizedBox(height: 12),
            Card(
              key: const Key('measure-result'),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (simulated) const SimulatedBadge(),
                    ReadingSummary(
                      kind: r.reading.kind,
                      values: r.reading.values,
                      flags: r.reading.flags,
                    ),
                    const SizedBox(height: 8),
                    if (r.refusal != null)
                      Text(l.measureRefused(r.refusal!),
                          key: const Key('measure-refused'),
                          style: TextStyle(
                              color: Theme.of(context).colorScheme.error))
                    else ...[
                      Text(l.measureNotRecord),
                      const SizedBox(height: 8),
                      FilledButton(
                        key: const Key('measure-save'),
                        onPressed: _save,
                        child: Text(l.measureSave),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],
          if (_notice != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_notice!, key: const Key('measure-notice')),
            ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_error!,
                  key: const Key('measure-error'),
                  style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
        ],
      ),
    );
  }
}
