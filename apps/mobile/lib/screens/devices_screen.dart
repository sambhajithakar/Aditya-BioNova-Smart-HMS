/// Settings → Medical devices (M8.2): the clinic's registered BP monitors and
/// pulse oximeters, pairing them with THIS phone, and (device.manage)
/// registering a newly scanned device.
///
/// Registration and pairing are online actions (the server is the
/// allow-list). The list is cached so capture works offline afterwards.
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../devices/transport.dart';
import '../l10n/l10n.dart';
import 'sync_widgets.dart';

String deviceKindLabel(BuildContext context, String? kind) =>
    kind == DeviceKinds.oximeter
        ? context.l10n.deviceKindOximeter
        : context.l10n.deviceKindBp;

class SimulatedBadge extends StatelessWidget {
  const SimulatedBadge({super.key});

  @override
  Widget build(BuildContext context) => Container(
        key: const Key('simulated-badge'),
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.tertiaryContainer,
          borderRadius: BorderRadius.circular(4),
        ),
        child: Text(context.l10n.deviceSimulated,
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
      );
}

class DevicesScreen extends StatefulWidget {
  const DevicesScreen({super.key, required this.graph, required this.access});

  final AppGraph graph;
  final DeviceAccess access;

  @override
  State<DevicesScreen> createState() => _DevicesScreenState();
}

class _DevicesScreenState extends State<DevicesScreen> {
  String? _notice;
  String? _error;
  bool _busy = false;
  List<Advertisement>? _found;
  String? _pairing; // registered device id being paired

  AppGraph get graph => widget.graph;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      await action();
    } catch (err) {
      if (mounted) setState(() => _error = err.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _refresh() async {
    if (graph.network.value.isOffline) return;
    await _run(() => graph.devices.refresh(graph.client));
  }

  Future<void> _scan({String? forDevice}) => _run(() async {
        final found = await graph.deviceTransport.scan();
        if (!mounted) return;
        setState(() {
          _found = found;
          _pairing = forDevice;
          if (found.isEmpty) _notice = context.l10n.deviceScanNone;
        });
      });

  Future<void> _choose(Advertisement ad) async {
    final pairing = _pairing;
    if (pairing != null) {
      await _run(() async {
        final ok = await graph.devices.pair(graph.client, pairing, ad.address);
        if (!mounted) return;
        setState(() {
          _found = null;
          _pairing = null;
          if (ok) {
            _notice = context.l10n.devicePairDone;
          } else {
            _error = context.l10n.devicePairMismatch;
          }
        });
      });
      return;
    }
    final label = await _askLabel(ad.name);
    if (label == null || !mounted) return;
    await _run(() async {
      final info = await graph.deviceTransport.readInfo(ad.address);
      await graph.devices.register(graph.client, ad: ad, label: label, info: info);
      if (!mounted) return;
      setState(() {
        _found = null;
        _notice = context.l10n.deviceRegistered;
      });
    });
  }

  Future<String?> _askLabel(String initial) {
    final ctl = TextEditingController(text: initial);
    return showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(ctx.l10n.deviceRegister),
        content: TextField(
          key: const Key('device-label'),
          controller: ctl,
          decoration: InputDecoration(labelText: ctx.l10n.deviceLabel),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: Text(ctx.l10n.cancel)),
          FilledButton(
            key: const Key('device-label-ok'),
            onPressed: () {
              final v = ctl.text.trim();
              if (v.length >= 2) Navigator.pop(ctx, v);
            },
            child: Text(ctx.l10n.deviceRegister),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final devices = graph.devices.active();
    return Scaffold(
      appBar: AppBar(title: Text(l.devicesTitle)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(l.devicesIntro),
          const SizedBox(height: 8),
          Text(l.devicesNotValidated,
              key: const Key('devices-not-validated'),
              style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 8),
          Wrap(spacing: 8, children: [
            OnlineOnlyButton(
              key: const Key('devices-refresh'),
              network: graph.network,
              label: l.devicesRefresh,
              onPressed: _busy ? null : _refresh,
            ),
            if (widget.access.manage)
              OnlineOnlyButton(
                key: const Key('devices-register'),
                network: graph.network,
                label: l.deviceRegister,
                onPressed: _busy ? null : () => _scan(),
              ),
          ]),
          if (_busy) const LinearProgressIndicator(),
          if (_notice != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_notice!, key: const Key('devices-notice')),
            ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_error!,
                  key: const Key('devices-error'),
                  style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          if (_found != null) ...[
            const SizedBox(height: 12),
            Text(l.deviceScan, style: Theme.of(context).textTheme.titleSmall),
            for (final ad in _found!)
              // pairing a registered device: only devices of its kind
              if (_pairing == null ||
                  ad.kind == graph.devices.active().firstWhere(
                      (d) => d['id'] == _pairing,
                      orElse: () => const {})['kind'])
              ListTile(
                key: Key('found-${ad.address}'),
                title: Text(ad.name),
                subtitle: Text(deviceKindLabel(context, ad.kind)),
                trailing: ad.simulated ? const SimulatedBadge() : null,
                onTap: _busy ? null : () => _choose(ad),
              ),
          ],
          const SizedBox(height: 12),
          if (devices.isEmpty) Text(l.devicesNone),
          for (final d in devices) _deviceTile(d),
        ],
      ),
    );
  }

  Widget _deviceTile(Map<String, dynamic> d) {
    final l = context.l10n;
    final id = '${d['id']}';
    final paired = graph.devices.isPaired(id);
    return Card(
      key: Key('device-$id'),
      child: ListTile(
        title: Row(children: [
          Flexible(child: Text('${d['label']}')),
          if (d['is_simulator'] == true) ...[
            const SizedBox(width: 6),
            const SimulatedBadge(),
          ],
        ]),
        subtitle: Text('${deviceKindLabel(context, d['kind'] as String?)} · '
            '${paired ? l.devicePaired : l.deviceNotPaired}'),
        trailing: paired
            ? TextButton(
                key: Key('device-unpair-$id'),
                onPressed: () async {
                  await graph.devices.unpair(id);
                  if (mounted) setState(() {});
                },
                child: Text(l.deviceUnpair),
              )
            : (widget.access.capture
                ? TextButton(
                    key: Key('device-pair-$id'),
                    onPressed: _busy || graph.network.value.isOffline
                        ? null
                        : () => _scan(forDevice: id),
                    child: Text(l.devicePair),
                  )
                : null),
      ),
    );
  }
}
