/// PIN screens (audit H22): set the local app-lock PIN after the first
/// online sign-in, and unlock with it on cold start / after inactivity.
///
/// Unlocking works with no network — that is what makes the offline
/// features reachable after a restart without signal. Too many wrong PINs
/// erase the PIN and the stored session, sending the user to the online
/// sign-in (offline work stays queued, tagged with its creator).
library;

import 'package:flutter/material.dart';

import '../app_graph.dart';
import '../auth/app_lock.dart';
import 'login_screen.dart';

enum LockMode { setPin, unlock }

class LockScreen extends StatefulWidget {
  const LockScreen({
    super.key,
    required this.graph,
    required this.mode,
    required this.onDone,
  });

  final AppGraph graph;
  final LockMode mode;

  /// Called (with this screen's context) once unlocked / the PIN is set.
  final void Function(BuildContext context) onDone;

  @override
  State<LockScreen> createState() => _LockScreenState();
}

class _LockScreenState extends State<LockScreen> {
  final _pin = TextEditingController();
  final _confirm = TextEditingController();
  String? _error;
  bool _busy = false;

  AppLock get _lock => widget.graph.appLock;

  @override
  void dispose() {
    _pin.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (widget.mode == LockMode.setPin) {
        await _setPin();
      } else {
        await _unlock();
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _setPin() async {
    final pin = _pin.text.trim();
    if (!AppLock.pinPattern.hasMatch(pin)) {
      setState(() => _error = 'Use 4 to 8 digits.');
      return;
    }
    if (pin != _confirm.text.trim()) {
      setState(() => _error = 'The two PINs do not match.');
      return;
    }
    await _lock.setPin(pin);
    if (!mounted) return;
    widget.onDone(context);
  }

  Future<void> _unlock() async {
    final result = await _lock.unlock(_pin.text.trim());
    if (!mounted) return;
    switch (result) {
      case UnlockResult.unlocked:
        widget.graph.scheduler.requestSync(force: true);
        widget.onDone(context);
      case UnlockResult.wrongPin:
        final left = await _lock.remainingAttempts();
        if (!mounted) return;
        _pin.clear();
        setState(() => _error =
            'Wrong PIN — $left attempt${left == 1 ? '' : 's'} left.');
      case UnlockResult.lockedOut:
        _toLogin('Too many wrong PINs. Sign in online again — work saved '
            'on this device is kept.');
    }
  }

  void _toLogin(String? message) {
    widget.graph.shellActive = false;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute<void>(
        builder: (_) => LoginScreen(graph: widget.graph, notice: message),
      ),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final setting = widget.mode == LockMode.setPin;
    final profile = widget.graph.session.cachedProfile;
    return PopScope(
      canPop: false,
      child: Scaffold(
        body: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(setting ? Icons.pin_outlined : Icons.lock_outline,
                      size: 40),
                  const SizedBox(height: 12),
                  Text(
                    setting ? 'Set an app PIN' : 'Enter your app PIN',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    setting
                        ? 'Patient data on this device is protected by a PIN. '
                            'You will need it to open the app, even with no '
                            'network.'
                        : [
                            if (profile != null && profile.email.isNotEmpty)
                              profile.email,
                            'Works offline.',
                          ].join(' · '),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 20),
                  TextField(
                    key: const Key('pin-entry'),
                    controller: _pin,
                    obscureText: true,
                    keyboardType: TextInputType.number,
                    maxLength: 8,
                    decoration: const InputDecoration(labelText: 'PIN'),
                    onSubmitted: setting ? null : (_) => _submit(),
                  ),
                  if (setting)
                    TextField(
                      key: const Key('pin-confirm'),
                      controller: _confirm,
                      obscureText: true,
                      keyboardType: TextInputType.number,
                      maxLength: 8,
                      decoration:
                          const InputDecoration(labelText: 'Repeat PIN'),
                    ),
                  if (_error != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        _error!,
                        key: const Key('pin-error'),
                        style: TextStyle(
                            color: Theme.of(context).colorScheme.error),
                      ),
                    ),
                  const SizedBox(height: 12),
                  FilledButton(
                    key: const Key('pin-submit'),
                    onPressed: _busy ? null : _submit,
                    child: Text(setting ? 'Save PIN' : 'Unlock'),
                  ),
                  if (!setting)
                    TextButton(
                      key: const Key('pin-use-password'),
                      onPressed: _busy ? null : () => _toLogin(null),
                      child: const Text('Sign in with password instead'),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
