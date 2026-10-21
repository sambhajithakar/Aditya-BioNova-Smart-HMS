/// LAN demo build only: choose the demo server on the owner's computer.
///
/// The address is checked before it is stored: the server must answer
/// `GET /api/v1/health` as the HMS API and must not report a production
/// environment (a demo phone never talks to production). Connecting
/// deletes this app's local data, which belonged to the previous server.
library;

import 'package:flutter/material.dart';

import '../api/transport.dart';
import '../boot.dart';
import '../demo/demo_server.dart';
import '../l10n/l10n.dart';

/// Checks that [url] is a usable HMS demo server (injectable for tests).
typedef DemoServerProbe = Future<DemoProbeResult> Function(String url);

enum DemoProbeResult { ok, unreachable, notHms, production }

Future<DemoProbeResult> probeDemoServer(String url) async {
  try {
    final r = await HttpTransport(
      baseUrl: url,
      timeout: const Duration(seconds: 8),
    ).send(method: 'GET', path: '/health');
    final json = r.json;
    if (r.status != 200 || json is! Map || json['status'] != 'ok') {
      return DemoProbeResult.notHms;
    }
    if (!'${json['service']}'.contains('Smart HMS')) {
      return DemoProbeResult.notHms;
    }
    if (json['environment'] == 'production') return DemoProbeResult.production;
    return DemoProbeResult.ok;
  } catch (_) {
    return DemoProbeResult.unreachable;
  }
}

class DemoServerScreen extends StatefulWidget {
  const DemoServerScreen({
    super.key,
    required this.request,
    required this.onOutcome,
    this.probe = probeDemoServer,
  });

  final BootNeedsDemoServer request;
  final ValueChanged<BootOutcome> onOutcome;
  final DemoServerProbe probe;

  @override
  State<DemoServerScreen> createState() => _DemoServerScreenState();
}

class _DemoServerScreenState extends State<DemoServerScreen> {
  late final _address = TextEditingController(
    text: widget.request.current?.replaceFirst(RegExp(r'^http://'), '') ?? '',
  );
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _address.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    final l = context.l10n;
    final url = normalizeDemoServer(_address.text);
    if (url == null) {
      setState(() => _error = l.demoServerInvalid);
      return;
    }
    setState(() {
      _error = null;
      _busy = true;
    });
    final result = await widget.probe(url);
    if (!mounted) return;
    if (result != DemoProbeResult.ok) {
      setState(() {
        _busy = false;
        _error = switch (result) {
          DemoProbeResult.production => l.demoServerProduction,
          DemoProbeResult.notHms => l.demoServerNotHms(url),
          _ => l.demoServerUnreachable(url),
        };
      });
      return;
    }
    final next = await widget.request.connect(url);
    if (mounted) widget.onOutcome(next);
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    return Scaffold(
      appBar: AppBar(title: Text(l.demoServerTitle)),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(l.demoServerHelp, key: const Key('demo-server-help')),
                const SizedBox(height: 16),
                TextField(
                  key: const Key('demo-server-address'),
                  controller: _address,
                  keyboardType: TextInputType.url,
                  autocorrect: false,
                  decoration: InputDecoration(
                    labelText: l.demoServerField,
                    hintText: '192.168.1.20:8000',
                  ),
                  onSubmitted: (_) => _connect(),
                ),
                const SizedBox(height: 8),
                Text(l.demoServerWipeWarning,
                    style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(height: 16),
                if (_error != null)
                  Text(
                    _error!,
                    key: const Key('demo-server-error'),
                    style: TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                const SizedBox(height: 8),
                FilledButton(
                  key: const Key('demo-server-connect'),
                  onPressed: _busy ? null : _connect,
                  child: Text(_busy ? l.demoServerChecking : l.demoServerConnect),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
